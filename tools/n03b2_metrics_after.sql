-- N03b-2: замер "после" (копия n03b2_metrics.sql с полями схемы 8). Запускать на stage после пересборки отчётов, как и замер "до":
--   psql ... -f n03b2_metrics_after.sql
-- Поля схемы 8: шаг плана — evidence (массив строк журнала), material {tasks[], on_lesson}, check {statement, task|null, on_lesson};
-- верхний уровень — checked_topics, more_difficulties; строка журнала — task_withdrawn.
-- Охранные CASE вместо AND: Postgres не гарантирует порядок AND, а у старых отчётов evidence — строка.
-- "До": у шага не было ни одного из этих ключей, evidence был строкой-кодом; поэтому те же формулы дают 0.
-- Срез: только отчёты схемы 8 (старые 'ready' до пересборки не смешиваются с замером "после"; их число — отдельным полем).
with r as (select id, report_json j from diag_reports
           where generation_status='ready' and coalesce(report_json->'report_meta'->>'report_schema_version','0')::int = 8),
steps as (
  select r.id, s from r,
  jsonb_array_elements(case when jsonb_typeof(r.j->'action_plan')='array' then r.j->'action_plan' else '[]'::jsonb end) s
),
-- навыки с ошибками в живых заданиях (задание, снятое из банка после попытки, не считается: оно помечено в журнале)
errs as (
  select r.id, e->>'skill_id' skill_id
  from r, jsonb_array_elements(case when jsonb_typeof(r.j->'error_patterns')='array' then r.j->'error_patterns' else '[]'::jsonb end) e
  where coalesce(e->>'eval_category','') not in ('correct','')
    and coalesce((e->>'task_withdrawn')::boolean, false) = false
  group by 1, 2
),
named as (
  select id, s->>'skill_id' skill_id from steps
  union
  select r.id, k->>'skill_id'
  from r,
       jsonb_array_elements(case when jsonb_typeof(r.j->'more_difficulties')='array' then r.j->'more_difficulties' else '[]'::jsonb end) g,
       jsonb_array_elements(case when jsonb_typeof(g->'skills')='array' then g->'skills' else '[]'::jsonb end) k
),
maps as (
  select r.id, sum((t->>'checked')::int) checked, sum((t->>'errors')::int) wrong
  from r, jsonb_array_elements(case when jsonb_typeof(r.j->'checked_topics')='array' then r.j->'checked_topics' else '[]'::jsonb end) t
  group by 1
)
select 'отчётов='||(select count(*) from r)
 ||' шагов='||(select count(*) from steps)
 ||' шагов_с_основанием='||(select count(*) from steps where case when jsonb_typeof(s->'evidence')='array' then jsonb_array_length(s->'evidence') else 0 end > 0)
 ||' шагов_с_материалом_из_банка='||(select count(*) from steps where jsonb_typeof(s->'material')='object'
        and case when jsonb_typeof(s->'material'->'tasks')='array' then jsonb_array_length(s->'material'->'tasks') else 0 end > 0)
 ||' шагов_материал_на_занятии='||(select count(*) from steps where jsonb_typeof(s->'material')='object' and s->'material'->>'on_lesson'='true')
 ||' шагов_без_материала_банк_не_прочитан='||(select count(*) from steps where jsonb_typeof(s->'material')<>'object' or s->'material' is null)
 ||' шагов_с_проверкой_заданием_банка='||(select count(*) from steps where jsonb_typeof(s->'check')='object' and s->'check'->>'statement' is not null
        and jsonb_typeof(s->'check'->'task')='object')
 ||' шагов_проверка_на_занятии='||(select count(*) from steps where jsonb_typeof(s->'check')='object' and s->'check'->>'statement' is not null
        and s->'check'->>'on_lesson'='true')
 ||' разных_описаний='||(select count(distinct s->>'full_description') from steps)
 ||' отчётов_с_кластерами='||(select count(*) from r where case when jsonb_typeof(j->'cognitive_error_types')='array' then jsonb_array_length(j->'cognitive_error_types') else 0 end > 0)
 ||' навыков_с_ошибками='||(select count(*) from errs)
 ||' из_них_нигде_не_названо='||(select count(*) from errs e where not exists (select 1 from named n where n.id=e.id and n.skill_id=e.skill_id))
 ||' карта_тем_есть='||(select count(*) from r where case when jsonb_typeof(j->'checked_topics')='array' then jsonb_array_length(j->'checked_topics') else 0 end > 0)
 ||' карта_сходится_с_шапкой='||(select count(*) from maps m join r using (id)
        where m.checked=(r.j->'report_meta'->>'total_questions')::int
          and m.wrong=(r.j->'report_meta'->>'total_questions')::int-(r.j->'report_meta'->>'questions_correct')::int)
 ||' первый_шаг_равен_старту='||(select count(*) from r where j->'recommended_start'->>'skill_id' = j->'action_plan'->0->>'skill_id')
 ||' шагов_коррекции='||(select count(*) from steps where s->>'kind'='correction')
 ||' шагов_коррекции_с_основанием_из_журнала_попытки='||(select count(*) from steps s2 join r using (id) where s2.s->>'kind'='correction'
        and case when jsonb_typeof(s2.s->'evidence')='array' then jsonb_array_length(s2.s->'evidence') else 0 end > 0
        and not exists (select 1 from jsonb_array_elements(case when jsonb_typeof(s2.s->'evidence')='array' then s2.s->'evidence' else '[]'::jsonb end) ev
                        where not exists (select 1 from jsonb_array_elements(case when jsonb_typeof(r.j->'error_patterns')='array' then r.j->'error_patterns' else '[]'::jsonb end) ep
                                          where ep->>'answer_id' = ev->>'answer_id')))
 ||' отчётов_других_схем_ready_не_в_срезе='||(select count(*) from diag_reports where generation_status='ready' and coalesce(report_json->'report_meta'->>'report_schema_version','0')::int <> 8)
 ||' шагов_с_основанием_из_снятых='||(select count(*) from steps s join r using (id)
        where exists (select 1
                      from jsonb_array_elements(case when jsonb_typeof(s.s->'evidence')='array' then s.s->'evidence' else '[]'::jsonb end) ev,
                           jsonb_array_elements(case when jsonb_typeof(r.j->'error_patterns')='array' then r.j->'error_patterns' else '[]'::jsonb end) ep
                      where ev->>'answer_id'=ep->>'answer_id' and coalesce((ep->>'task_withdrawn')::boolean, false)));
select 'категории_ошибок: '||string_agg(c||'='||n, ', ') from (select e->>'eval_category' c, count(*) n from diag_reports d, jsonb_array_elements(d.report_json->'error_patterns') e where d.generation_status='ready' group by 1) x;
