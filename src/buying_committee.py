"""Title-based buying-committee roles and the sequence angle each role receives."""
import re

ROLES = {
    'executive': {
        'label': 'Executive sponsor',
        'examples': 'COO, CEO, VP Supply Chain, Chief Logistics Officer',
        'angle': 'Business outcome: consistency across markets and what the change costs the operation.',
        'touch_2': 'That is a number worth seeing at leadership level before scoping any change.',
        'touch_3': 'The useful check is whether it fits the systems and carriers already in place, without a replatforming project.',
    },
    'end_user': {
        'label': 'Operational end user',
        'examples': 'Head of Logistics, Head of Ecommerce, Supply Chain Manager, Director of Operations',
        'angle': 'Day-to-day workflow: the manual steps, exceptions and handoffs the team runs today.',
        'touch_2': 'Your team could run that check on one real order this week.',
        'touch_3': 'The useful check is how the exceptions and handoffs your team handles by hand would run instead.',
    },
    'technical': {
        'label': 'Technical evaluator',
        'examples': 'CTO, Chief Digital Officer, Head of Integration, IT Director',
        'angle': 'Integration: how orders, labels and carrier events move between existing systems.',
        'touch_2': 'That check runs across the systems holding orders, labels and carrier events.',
        'touch_3': 'The useful check is how the handoff from your order system would integrate with ShippyPro\'s shipping APIs.',
    },
}

TECHNICAL = re.compile(r'\bcto\b|technolog|integration|\bit\b|engineering|chief digital|(?:senior )?vice president,? digital|\bsvp digital|\bcdo\b', re.I)
EXECUTIVE = re.compile(r'chief|\bceo\b|\bcoo\b|\bcso\b|founder|president|\b[es]?vp\b|managing director', re.I)


def classify(title):
    """Map a job title to one committee role. Technical wins, then seniority; the rest operate."""
    title = title or ''
    if TECHNICAL.search(title):
        return 'technical'
    if EXECUTIVE.search(title):
        return 'executive'
    return 'end_user'


def describe(title):
    key = classify(title)
    return dict(ROLES[key], role=key, basis='Inferred from the reported job title; confirm buying authority before outreach.')


def coverage(contacts):
    """Roles held per account and the roles still missing, for multi-threading."""
    accounts = {}
    for c in contacts:
        accounts.setdefault(c['domain'], {'company': c['company'], 'roles': set()})['roles'].add(classify(c.get('title')))
    rows = [{'domain': d, 'company': a['company'], 'roles': sorted(a['roles']),
             'missing': [r for r in ROLES if r not in a['roles']]} for d, a in accounts.items()]
    totals = {r: sum(classify(c.get('title')) == r for c in contacts) for r in ROLES}
    return {'by_role': totals, 'accounts': len(rows), 'multi_threaded_accounts': sum(len(r['roles']) > 1 for r in rows), 'rows': rows}
