from datetime import timedelta

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.rusclimate.api.router import ConnMode
from custom_components.rusclimate.const import DOMAIN
from custom_components.rusclimate.health import LOCAL_DOWN_GRACE, issue_id

from .conftest import make_entry


def _issue(hass, entry):
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id(entry))


async def _wait(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_issue_after_long_local_outage_and_cleared_on_return(hass, loaded, freezer):
    entry, ch = loaded
    ch["cloud"].set_up(True)
    ch["local"].set_up(False)
    await _wait(hass, freezer, LOCAL_DOWN_GRACE - timedelta(minutes=1))
    assert _issue(hass, entry) is None

    await _wait(hass, freezer, timedelta(minutes=2))
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == "local_unreachable_cloud"
    assert issue.translation_placeholders == {"name": "Office"}

    ch["local"].set_up(True)
    await hass.async_block_till_done()
    assert _issue(hass, entry) is None


async def test_short_outage_raises_nothing(hass, loaded, freezer):
    entry, ch = loaded
    ch["local"].set_up(False)
    await _wait(hass, freezer, timedelta(minutes=10))
    ch["local"].set_up(True)
    await _wait(hass, freezer, LOCAL_DOWN_GRACE * 2)
    assert _issue(hass, entry) is None


async def test_no_channel_at_all_uses_offline_wording(hass, loaded, freezer):
    entry, ch = loaded
    ch["local"].set_up(False)
    await _wait(hass, freezer, LOCAL_DOWN_GRACE + timedelta(minutes=1))
    assert _issue(hass, entry).translation_key == "local_unreachable"


async def test_unload_removes_issue(hass, loaded, freezer):
    entry, ch = loaded
    ch["local"].set_up(False)
    await _wait(hass, freezer, LOCAL_DOWN_GRACE + timedelta(minutes=1))
    assert _issue(hass, entry) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert _issue(hass, entry) is None


async def test_cloud_only_is_not_monitored(hass, channels, freezer):
    entry = make_entry(ConnMode.CLOUD)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _wait(hass, freezer, LOCAL_DOWN_GRACE * 2)
    assert _issue(hass, entry) is None
