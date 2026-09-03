import re

import pytest


class TestAPIWT:
    @pytest.mark.asyncio(scope="session")
    async def test_get_whitelist_token(self, base_cli_config_api):
        api = base_cli_config_api
        response = await api.get_wt()
        assert len(response) == 64

    @pytest.mark.asyncio(scope="session")
    async def test_get_whitelist_token_debug(self, base_cli_config_api_debug_save_js_locally):
        api = base_cli_config_api_debug_save_js_locally
        # TODO: get the names and modified times
        response = await api.get_wt()
        assert len(response) == 64
        # TODO: Check that a new file appears or last modified time changed
