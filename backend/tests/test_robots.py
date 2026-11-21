import pytest

from app.robots import RobotsPolicy


@pytest.mark.parametrize('path,allowed', [
    ('/careers?location=India', True), ('/api/pcsx/search', True),
    ('/api/pcsx/position_details?position_id=42', True),
    ('/private', False), ('/', True), ('/anything', False),
])
def test_employer_allow_exceptions_override_root_disallow(path, allowed):
    policy = RobotsPolicy('User-agent: *\nDisallow: /\nAllow: /$\nAllow: /careers\nAllow: /api/pcsx'.splitlines())
    assert policy.can_fetch('LaunchpadJobCollector/1.0', 'https://example.com' + path) is allowed


@pytest.mark.parametrize('path,allowed', [
    ('/careers/results?location=India', True), ('/careers/results?page=1', False),
    ('/careers/results?location=India&page=2', False), ('/public', True), ('/public/more', False),
])
def test_wildcards_and_terminal_anchors(path, allowed):
    policy = RobotsPolicy('User-agent: *\nDisallow: /careers/results?*page=\nDisallow: /public\nAllow: /public$'.splitlines())
    assert policy.can_fetch('LaunchpadJobCollector/1.0', 'https://example.com' + path) is allowed


def test_specific_agent_groups_merge_and_allow_wins_ties():
    policy = RobotsPolicy('User-agent: *\nDisallow: /\nUser-agent: LaunchpadJobCollector\nDisallow: /private\nUser-agent: launchpadjobcollector\nAllow: /private\nDisallow: /hidden'.splitlines())
    assert policy.can_fetch('LaunchpadJobCollector/1.0', 'https://example.com/normal')
    assert policy.can_fetch('LaunchpadJobCollector/1.0', 'https://example.com/private')
    assert not policy.can_fetch('LaunchpadJobCollector/1.0', 'https://example.com/hidden')
    assert not policy.can_fetch('Other/1.0', 'https://example.com/normal')


def test_encoded_paths_and_empty_disallow():
    policy = RobotsPolicy('User-agent: *\nDisallow:\nDisallow: /café\nDisallow: /private/~user\nDisallow: /encoded%2Fslash'.splitlines())
    assert not policy.can_fetch('Bot', 'https://example.com/caf%C3%A9')
    assert not policy.can_fetch('Bot', 'https://example.com/private/%7Euser')
    assert not policy.can_fetch('Bot', 'https://example.com/encoded%2fslash')
    assert policy.can_fetch('Bot', 'https://example.com/encoded/slash')
