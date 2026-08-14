"""
Backfill distractor_explanation_latex for 110 error_patterns in diag_reports
where distractor_explanation is null.
Uses Gemini to generate personalized, pedagogically grounded explanations.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import psycopg2
import google.generativeai as genai

log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, '/Users/arslan/Desktop/ALGO/diagnostic-service')
from src.core.config import get_settings
settings = get_settings()

genai.configure(api_key=settings.gemini_api_key)
_model = genai.GenerativeModel("gemini-2.0-flash")

# ─── DB ───────────────────────────────────────────────────────────────────────
conn = psycopg2.connect(
    dbname='algo_diagnostic', user='algo',
    password='algo_password', host='127.0.0.1', port=5433
)
cur = conn.cursor()


def generate_explanation(ep: dict) -> Optional[str]:
    """Generate a personalized distractor explanation for one error_pattern."""
    q = ep.get('question_latex') or ep.get('question_text') or ''
    correct = ep.get('correct_answer_latex') or ep.get('correct_answer') or ''
    student = ep.get('student_answer_latex') or ep.get('student_answer') or ''
    skill = ep.get('skill_name_ru') or ''

    prompt = f"""Ты — педагогический эксперт. Ученик допустил ошибку в математической задаче.

Задача: {q}
Правильный ответ: {correct}
Ответ ученика (ошибочный дистрактор): {student}
Навык: {skill}

Напиши персональное объяснение ошибки ученика (2-3 предложения, 40-80 слов).
Объясни КОНКРЕТНО, какую логическую или вычислительную ошибку совершил ученик, выбрав этот дистрактор.
Используй LaTeX в формате $...$ для формул.
Верни ТОЛЬКО текст объяснения, без JSON, без заголовков."""

    try:
        resp = _model.generate_content(prompt)
        text = resp.text.strip() if resp.text else ''
        if len(text) > 20:
            return text
    except Exception as e:
        log.error(f"Gemini error: {e}")
    return None


def main():
    cur.execute("SELECT id, report_json FROM diag_reports;")
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
            expl_latex = ep.get('distractor_explanation_latex') or ''

            if expl.strip() and len(expl.strip()) > 20:
                total_skipped += 1
                continue  # Already has explanation

            # Generate
            task_id = ep.get('task_id', '?')
            print(f"  ⚙️  Generating explanation for task {task_id}...")
            new_expl = generate_explanation(ep)
            time.sleep(0.3)  # Rate limit

            if new_expl:
                ep['distractor_explanation'] = new_expl
                ep['distractor_explanation_latex'] = new_expl
                changed = True
                total_filled += 1
                print(f"  ✅ {task_id}: {new_expl[:60]}...")
            else:
                print(f"  ⚠️  {task_id}: failed to generate")

        if changed:
            cur.execute(
                "UPDATE diag_reports SET report_json = %s WHERE id = %s;",
                (json.dumps(rj, ensure_ascii=False), report_id)
            )
            conn.commit()
            total_reports_updated += 1
            print(f"  💾 Report {report_id} updated")

    print(f"\n=== ИТОГ ===")
    print(f"✅ Объяснений сгенерировано:  {total_filled}")
    print(f"⏭️  Уже были (пропущено):       {total_skipped}")
    print(f"💾 Отчётов обновлено:           {total_reports_updated}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
