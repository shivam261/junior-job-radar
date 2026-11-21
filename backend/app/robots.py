"""Robots path rules with longest-match, Allow ties, wildcards and end anchors.

These rules matter for Eightfold: it disallows / and then explicitly allows
/careers and /api/pcsx. urllib.robotparser uses the first matching rule instead.
Reference: RFC 9309 sections 2.2.1-2.2.3.
"""
import re
from urllib.parse import quote, urlsplit

UNRESERVED = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')


def normalized_path(value):
    value = quote(value, safe="/%:*?$=&;+!,@'()[]-._~")
    return re.sub(r'%([0-9A-Fa-f]{2})', lambda match:
                  chr(int(match[1], 16)) if chr(int(match[1], 16)) in UNRESERVED
                  else '%' + match[1].upper(), value)


class RobotsPolicy:
    def __init__(self, lines):
        self.groups = []
        agents, rules, has_rules = [], [], False
        for line in lines:
            key, sep, value = line.split('#', 1)[0].partition(':')
            if not sep:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == 'user-agent':
                if has_rules:
                    self.groups.append((agents, rules))
                    agents, rules, has_rules = [], [], False
                agents.append(value.lower())
            elif key in ('allow', 'disallow') and agents:
                has_rules = True
                if value.startswith('/'):
                    rules.append((normalized_path(value), key == 'allow'))
        if agents:
            self.groups.append((agents, rules))

    def can_fetch(self, user_agent, url):
        product = user_agent.split('/', 1)[0].lower()
        matching = [rules for agents, rules in self.groups if product in agents]
        if not matching:
            matching = [rules for agents, rules in self.groups if '*' in agents]
        parsed = urlsplit(url)
        path = normalized_path((parsed.path or '/') + ('?' + parsed.query if parsed.query else ''))
        best = (-1, True)
        for rules in matching:
            for rule, allow in rules:
                anchored = rule.endswith('$')
                body = rule[:-1] if anchored else rule
                pattern = '^' + '.*'.join(re.escape(part) for part in body.split('*'))
                if anchored:
                    pattern += '$'
                if re.search(pattern, path):
                    octets = len(re.sub(r'%[0-9A-F]{2}', 'x', body.replace('*', '')))
                    best = max(best, (octets, allow))
        return best[1]
