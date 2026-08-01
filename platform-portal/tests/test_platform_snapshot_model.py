def test_platform_snapshot_model_scaffold_exists():
    from portal.models.platform_snapshot import PlatformSnapshot

    assert PlatformSnapshot.__tablename__ == "platform_snapshots"
