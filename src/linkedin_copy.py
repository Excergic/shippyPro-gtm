"""Connection-first LinkedIn drafts grounded in the existing ShippyPro research."""
import hashlib
import json

LABELS = ['Connection request', 'Follow-up 1', 'Follow-up 2', 'Follow-up 3']
OFFSETS = [0, 2, 6, 12]
SCOPES = {'routing': 'carrier rules', 'tracking': 'shipment visibility', 'api': 'shipping APIs', 'invoice': 'carrier invoice checks'}


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def validate(body, step):
    if not isinstance(body, str) or not body.strip():
        raise ValueError('LinkedIn message cannot be empty')
    if len(body.split()) >= 300:
        raise ValueError('LinkedIn messages must be under 300 words')
    if step == 1 and len(body.encode('utf-16-le')) // 2 > 200:
        raise ValueError('Keep the connection note within the configured 200-character budget')


def drafts(contact_id, row, angle, hook, feature, demo_url):
    if not hook or not isinstance(hook, str):
        raise ValueError('Missing reviewed LinkedIn event hook for ' + row['domain'])
    connection = (f"Hi {angle['greeting']}, {hook} caught my eye. "
                  f"I'm exploring ShippyPro's {SCOPES[angle['feature']]} for changes like this. Open to connecting?")
    diagnostic = angle['diagnostic'][0].upper() + angle['diagnostic'][1:]
    bodies = [connection,
        f"Thanks for connecting, {angle['greeting']}. {angle['opener']}\n\n{angle['question']}",
        f"One practical check: {diagnostic}. Look at {angle['metric']}.\n\n{feature['claim']} Would that be a useful check in {row['company']}'s setup?",
        f"Would it be useful to see {feature['scenario']} against {row['company']}'s actual systems? "
        f"A ShippyPro demo could focus on this: {angle['diagnostic']}.\n\n"
        f"If this is already covered, happy to leave it here. Otherwise, here's ShippyPro's public demo form: {demo_url}"]
    if sum(len(body.split()) for body in bodies) >= 300:
        raise ValueError('Keep the full suggested LinkedIn sequence under 300 words')
    result = []
    for index, body in enumerate(bodies):
        validate(body, index + 1)
        result.append({'id': contact_id + '-li-' + str(index + 1), 'step': index + 1,
                       'channel': 'linkedin', 'subject': LABELS[index], 'body': body,
                       'day_offset': OFFSETS[index], 'timing': 'With the invitation' if index == 0 else f'{OFFSETS[index]} business days after acceptance, only if no reply',
                       'evidence': [row['source_url'], row['linkedin'], feature['url']],
                       'content_hash': fingerprint(body), 'review_status': 'draft', 'edited': 0, 'revision': 1})
    return result


def merge(existing, generated):
    """Regenerate defaults without discarding any operator's edited copy."""
    old = {item['id']: item for item in existing}
    output = []
    changed = False
    for message in generated:
        prior = old.get(message['id'])
        if prior and prior.get('edited'):
            output.append(prior)
        elif prior and prior['content_hash'] == message['content_hash']:
            output.append(prior)
        else:
            if prior:
                message['revision'] = prior['revision'] + 1
            output.append(message)
            changed = True
    return output, changed


def edit(existing, message_id, revision, body):
    output = json.loads(json.dumps(existing))
    message = next((item for item in output if item['id'] == message_id), None)
    if not message:
        raise ValueError('Unknown LinkedIn draft for contact')
    if message['revision'] != revision:
        raise ValueError('Draft changed since it was opened; refresh before saving')
    if not isinstance(body, str):
        raise ValueError('LinkedIn message must be plain text')
    body = body.strip()
    validate(body, message['step'])
    message.update(body=body, content_hash=fingerprint(body), edited=1,
                   revision=message['revision'] + 1, review_status='draft')
    return output
