"""Workspace-local Google request estimates, never Google billing measurements.

Persist an uncertain entry BEFORE every attempt so a timeout, process interruption,
or subsequent local validation/storage failure cannot silently erase possible use.
Only a returned API response confirms submission; it does not confirm a charge.
No uploaded text, provider responses, or credentials belong in this ledger.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


REPORTING_TIMEZONE = 'America/Toronto'
DEFAULT_ALLOWANCE = 500_000
RATE_PER_MILLION = 20.0


class GoogleTranslationUsage:
    def __init__(self, store, project, *, clock=None):
        self.store, self.project = store, project
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def month(self):
        return self.clock().astimezone(ZoneInfo(REPORTING_TIMEZONE)).strftime('%Y-%m')

    def allowance(self):
        with self.store.connect() as db:
            row = db.execute('SELECT allowance FROM google_translation_usage_settings WHERE project=?',
                             (self.project,)).fetchone()
        return row[0] if row else DEFAULT_ALLOWANCE

    def set_allowance(self, characters):
        if isinstance(characters, bool) or not isinstance(characters, int) or characters < 0:
            raise ValueError('Enter a non-negative whole number of characters.')
        with self.store.connect() as db:
            db.execute('INSERT INTO google_translation_usage_settings VALUES (?,?) '
                       'ON CONFLICT(project) DO UPDATE SET allowance=excluded.allowance',
                       (self.project, characters))

    def start_request(self, characters, operation='translation'):
        if operation not in ('detection', 'translation'):
            raise ValueError('Choose detection or translation usage.')
        if isinstance(characters, bool) or not isinstance(characters, int) or characters <= 0:
            raise ValueError('Request usage must be a positive whole number of characters.')
        instant = self.clock()
        month = instant.astimezone(ZoneInfo(REPORTING_TIMEZONE)).strftime('%Y-%m')
        with self.store.connect() as db:
            cursor = db.execute('INSERT INTO google_translation_usage '
                                '(project,month,submitted_at,characters,status,operation) VALUES (?,?,?,?,?,?)',
                                (self.project, month, instant.astimezone(timezone.utc).isoformat(),
                                 characters, 'uncertain', operation))
            return cursor.lastrowid

    def confirm_request(self, request_id):
        with self.store.connect() as db:
            db.execute("UPDATE google_translation_usage SET status='confirmed' WHERE project=? AND id=?",
                       (self.project, request_id))

    def summary(self, month=None):
        period = month or self.month()
        with self.store.connect() as db:
            rows = db.execute('SELECT status, SUM(characters), COUNT(*) FROM google_translation_usage '
                              'WHERE project=? AND month=? GROUP BY status', (self.project, period)).fetchall()
            details = db.execute('SELECT operation,status,SUM(characters),COUNT(*) FROM google_translation_usage '
                                 'WHERE project=? AND month=? GROUP BY operation,status', (self.project, period)).fetchall()
        operations = {name: {'confirmed_characters': 0, 'uncertain_characters': 0, 'requests': 0,
                             'estimated_before_credits': 0.0} for name in ('detection', 'translation')}
        for operation, status, characters, requests in details:
            operations[operation][f'{status}_characters'] += characters
            operations[operation]['requests'] += requests
            operations[operation]['estimated_before_credits'] += characters * RATE_PER_MILLION / 1_000_000
        counts = {status: characters for status, characters, _ in rows}
        confirmed, uncertain = counts.get('confirmed', 0), counts.get('uncertain', 0)
        total, allowance = confirmed + uncertain, self.allowance()
        return {'month': period, 'operations': operations, 'confirmed_characters': confirmed, 'uncertain_characters': uncertain,
                'total_characters': total, 'requests': sum(count for _, _, count in rows),
                'allowance': allowance, 'remaining_characters': max(0, allowance - total),
                'estimated_before_credits': total * RATE_PER_MILLION / 1_000_000,
                'estimated_after_credits': max(0, total - allowance) * RATE_PER_MILLION / 1_000_000,
                'progress': min(1.0, total / allowance) if allowance else (1.0 if total else 0.0),
                'warning': total >= min(400_000, allowance * 0.8) if allowance else total > 0}

    def history(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT month, '
                              "SUM(CASE WHEN status='confirmed' THEN characters ELSE 0 END), "
                              "SUM(CASE WHEN status='uncertain' THEN characters ELSE 0 END), COUNT(*) "
                              'FROM google_translation_usage WHERE project=? GROUP BY month ORDER BY month DESC',
                              (self.project,)).fetchall()
        return [{'Month': month, 'Confirmed characters': confirmed, 'Uncertain characters': uncertain,
                 'API request attempts': requests} for month, confirmed, uncertain, requests in rows]

    def estimate_batch(self, characters, attempts=3):
        monthly = self.summary()
        remaining = monthly['remaining_characters']
        return {'before_credits': characters * RATE_PER_MILLION / 1_000_000,
                'after_credits': max(0, characters - remaining) * RATE_PER_MILLION / 1_000_000,
                'retry_before_credits': characters * attempts * RATE_PER_MILLION / 1_000_000,
                'retry_after_credits': max(0, characters * attempts - remaining) * RATE_PER_MILLION / 1_000_000}

    def operation_history(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT month,operation, '
                              "SUM(CASE WHEN status='confirmed' THEN characters ELSE 0 END), "
                              "SUM(CASE WHEN status='uncertain' THEN characters ELSE 0 END), COUNT(*) "
                              'FROM google_translation_usage WHERE project=? GROUP BY month,operation ORDER BY month DESC,operation',
                              (self.project,)).fetchall()
        return [{'Month': month, 'Operation': operation, 'Confirmed characters': confirmed,
                 'Uncertain characters': uncertain, 'API request attempts': requests,
                 'Estimated USD before credits': (confirmed + uncertain) * RATE_PER_MILLION / 1_000_000}
                for month, operation, confirmed, uncertain, requests in rows]
