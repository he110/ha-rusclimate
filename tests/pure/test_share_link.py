import pytest

from rc.api.share_link import InvalidShareLink, format_mac, parse_share_link

LINK = (
    "rusklimat://device-share/rusclimate/69/112233445566?token=0123456789ABCDEF0123456789ABCDEF"
    "&name=Ballu%20ONEAIR%20ASP-100&deviceLocation=Home&deviceRoom=%D0%94%D0%B5%D1%82%D1%81%D0%BA%D0%B0%D1%8F"
    "&attributes_model=ballu_asp"
)


def test_parses_all_fields():
    link = parse_share_link(LINK)
    assert link.vendor == "rusclimate"
    assert link.device_type == 69
    assert link.mac == "112233445566"
    assert link.token == "0123456789abcdef0123456789abcdef"
    assert link.name == "Ballu ONEAIR ASP-100"
    assert link.room == "Детская"
    assert link.location == "Home"
    assert link.model == "ballu_asp"


def test_link_inside_text():
    assert parse_share_link(f"Смотри: {LINK} ").mac == "112233445566"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "https://example.com",
        "rusklimat://device-share/rusclimate/69/112233445566",
        "rusklimat://device-share/rusclimate/69/112233445566?token=short",
        "rusklimat://device-share/rusclimate/xx/112233445566?token=0123456789abcdef0123456789abcdef",
        "rusklimat://device-share/rusclimate/69/zz?token=0123456789abcdef0123456789abcdef",
    ],
)
def test_rejects_garbage(text):
    with pytest.raises(InvalidShareLink):
        parse_share_link(text)


def test_format_mac():
    assert format_mac("112233445566") == "11:22:33:44:55:66"
