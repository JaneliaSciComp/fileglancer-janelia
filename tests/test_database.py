import tempfile
import os
import shutil
from datetime import datetime

import pytest
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fileglancer.database import Base, FileSharePathDB, LastRefreshDB
from fileglancer.utils import slugify_path
from fileglancer_janelia.update_db import _compare_datetimes, update_file_share_paths


def create_file_share_path_dicts(df):
    """Helper function to create file share path dictionaries from DataFrame"""
    return [{
        'name': slugify_path(row.linux_path),
        'zone': row.lab,
        'group': row.group,
        'storage': row.storage,
        'mount_path': row.linux_path,
        'mac_path': row.mac_path,
        'windows_path': row.windows_path,
        'linux_path': row.linux_path,
    } for row in df.itertuples(index=False)]


@pytest.fixture
def temp_dir():
    temp_dir = tempfile.mkdtemp()
    print(f"Created temp directory: {temp_dir}")
    yield temp_dir
    # Clean up the temp directory
    print(f"Cleaning up temp directory: {temp_dir}")
    shutil.rmtree(temp_dir)


@pytest.fixture
def db_session(temp_dir):
    """Create a test database session"""

    # Create temp directory for test database
    db_path = os.path.join(temp_dir, "test.db")

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)
    yield session

    # Clean up after each test
    session.query(FileSharePathDB).delete()
    session.query(LastRefreshDB).delete()
    session.commit()
    session.close()


def test_file_share_paths(db_session):
    # Create test data
    data = {
        'lab': ['lab1', 'lab2'],
        'group': ['group1', 'group2'],
        'storage': ['storage1', 'storage2'],
        'linux_path': ['/path1', '/path2'],
        'mac_path': ['mac1', 'mac2'],
        'windows_path': ['win1', 'win2']
    }
    df = pd.DataFrame(data)

    # Test update_file_share_paths
    paths = create_file_share_path_dicts(df)
    update_file_share_paths(db_session, paths, datetime.now())

    # Test retrieving paths
    all_paths = db_session.query(FileSharePathDB).all()
    assert len(all_paths) == 2
    assert all_paths[0].zone == 'lab1'
    assert all_paths[1].zone == 'lab2'

    # Test updating existing paths
    data['lab'] = ['lab1_updated', 'lab2_updated']
    df = pd.DataFrame(data)
    paths = create_file_share_path_dicts(df)
    update_file_share_paths(db_session, paths, datetime.now())

    all_paths = db_session.query(FileSharePathDB).all()
    assert all_paths[0].zone == 'lab1_updated'
    assert all_paths[1].zone == 'lab2_updated'


def test_last_refresh(db_session):
    now = datetime.now()
    data = {'lab': ['lab1'], 'group': ['group1'], 'storage': ['storage1'],
            'linux_path': ['/path1'], 'mac_path': ['mac1'], 'windows_path': ['win1']}
    df = pd.DataFrame(data)

    paths = create_file_share_path_dicts(df)
    update_file_share_paths(db_session, paths, now)

    refresh = db_session.query(LastRefreshDB).filter_by(table_name="file_share_paths").first()
    assert refresh is not None
    assert _compare_datetimes(refresh.source_last_updated, now)


def test_max_paths_to_delete(db_session):
    # Create initial data
    data = {
        'lab': ['lab1', 'lab2', 'lab3'],
        'group': ['group1', 'group2', 'group3'],
        'storage': ['storage1', 'storage2', 'storage3'],
        'linux_path': ['/path1', '/path2', '/path3'],
        'mac_path': ['mac1', 'mac2', 'mac3'],
        'windows_path': ['win1', 'win2', 'win3']
    }
    df = pd.DataFrame(data)
    paths = create_file_share_path_dicts(df)
    update_file_share_paths(db_session, paths, datetime.now())

    # Update with fewer paths (should trigger deletion limit)
    data = {
        'lab': ['lab1'],
        'group': ['group1'],
        'storage': ['storage1'],
        'linux_path': ['/path1'],
        'mac_path': ['mac1'],
        'windows_path': ['win1']
    }
    df = pd.DataFrame(data)
    paths = create_file_share_path_dicts(df)
    # With max_paths_to_delete=1, should not delete paths
    update_file_share_paths(db_session, paths, datetime.now(), max_paths_to_delete=1)
    all_paths = db_session.query(FileSharePathDB).all()
    assert len(all_paths) == 3  # Should still have all paths
