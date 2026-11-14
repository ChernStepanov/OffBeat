def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs internet (live CMR search)")
