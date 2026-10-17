"""
Backfill distractor_explanation for 110 error_patterns in diag_reports.
Uses DeepSeek (proven working in content-service).
"""
from __future__ import annotations

import json
import os
import sys
import time

import psycopg2
from dotenv import load_dotenv

# Load content-service .env so Azure/DeepSeek keys are available
load_dotenv('/Users/arslan/Desktop/ALGO/content-service/.env', override=True)

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model


conn = psycopg2.connect(
    dbname='algo_diagnostic', user='algo',
    password='algo_password', host='127.0.0.1', port=5433,
    options='-c timezone=UTC',  # session TimeZone=UTC (ROADMAP #49)
)
cur = conn.cursor()


def generate_explanation(ep: dict) -> str | None:
    q = ep.get('question_latex') or ep.get('question_text') or ''
    correct = ep.get('correct_answer_latex') or ep.get('correct_answer') or ''
    student = ep.get('student_answer_latex') or ep.get('student_answer') or ''
    skill = ep.get('skill_name_ru') or ''

    prompt = f"""Ты — педагогический математик. Ученик выбрал неверный дистрактор в задаче.

Задача: {q}
Правильный ответ: {correct}
Ответ ученика (ошибочный): {student}
Тема: {skill}

Напиши персональное объяснение конкретной ошибки ученика. 2-3 предложения (40-80 слов).
Объясни КАКУЮ именно ошибку допустил ученик, выбрав этот ответ вместо правильного.
Используй LaTeX в $...$ для формул.
Верни только текст объяснения, без JSON."""

    try:
        res = call_deepseek(prompt, model=get_deepseek_model(), temperature=0.15)
        if res and isinstance(res, str) and len(res.strip()) > 20:
            return res.strip()
    except Exception as e:
        print(f"    Error calling DeepSeek: {e}")
    return None


def main():
    cur.execute("SELECT id, report_json FROM diag_reports ORDER BY generated_at;")
    reports = cur.fetchall()

    total_filled = 0
    total_skipped = 0
    total_reports_updated = 0

    for report_id, rj in reports:
        if isinstance(rj, str):
            rj = json.loads(rj)
        if not rj or not isinstance(rj, dict):
            continue

        eps = rj.get('error_patterns', [])
        changed = False

        for ep in eps:
            if not isinstance(ep, dict):
                continue
            if ep.get('eval_category') != 'distractor':
                continue

            expl = ep.get('distractor_explanation') or ''
            if expl.strip() and len(expl.strip()) > 20:
                total_skipped += 1
                continue

            task_id = ep.get('task_id', '?')
            print(f"  ⚙️  {task_id}...")
            new_expl = generate_explanation(ep)
            time.sleep(0.5)

            if new_expl:
                ep['distractor_explanation'] = new_expl
                ep['distractor_explanation_latex'] = new_expl
                changed = True
                total_filled += 1
                print(f"  ✅ {task_id}: {new_expl[:70]}...")
            else:
                print(f"  ⚠️  {task_id}: generation failed — keeping null")

        if changed:
            cur.execute(
                "UPDATE diag_reports SET report_json = %s WHERE id = %s;",
                (json.dumps(rj, ensure_ascii=False), report_id)
            )
            conn.commit()
            total_reports_updated += 1
            print(f"  💾 Report {report_id} saved")

    print(f"\n=== ИТОГ ===")
    print(f"✅ Сгенерировано:    {total_filled}")
    print(f"⏭️  Уже были:         {total_skipped}")
    print(f"💾 Отчётов обновлено: {total_reports_updated}")

    # Final count
    cur.execute("SELECT report_json FROM diag_reports;")
    null_after = 0
    for (rj_row,) in cur.fetchall():
        if isinstance(rj_row, str): rj_row = json.loads(rj_row)
        for ep in (rj_row or {}).get('error_patterns', []):
            if ep.get('eval_category') == 'distractor' and not (ep.get('distractor_explanation') or '').strip():
                null_after += 1
    print(f"🔍 Оставшихся null explanation после backfill: {null_after}")


if __name__ == '__main__':
    main()
