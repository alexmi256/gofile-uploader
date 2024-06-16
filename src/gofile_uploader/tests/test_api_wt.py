import re

import pytest


class TestAPIWT:
    @pytest.mark.asyncio(scope="session")
    async def test_get_whitelist_token(self, base_cli_config_api):
        api = base_cli_config_api
        response = await api.get_wt()
        assert re.match(r"[a-zA-Z0-9]{12}", response)

    @pytest.mark.asyncio(scope="session")
    async def test_get_whitelist_token_debug(self, base_cli_config_api_debug_save_js_locally):
        api = base_cli_config_api_debug_save_js_locally
        response = await api.get_wt()
        assert re.match(r"[a-zA-Z0-9]{12}", response)
