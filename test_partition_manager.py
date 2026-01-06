#!/usr/bin/env python3
"""
Test suite for Partition Management Tool
"""

import sys
import os

# Add the parent directory to the path so we can import partition_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from partition_manager import PartitionManager


def test_size_conversion():
    """Test size conversion utilities."""
    print("Testing size conversion...")
    manager = PartitionManager()
    
    # Test human to bytes
    assert manager.human_to_bytes('1KB') == 1024
    assert manager.human_to_bytes('1MB') == 1024 ** 2
    assert manager.human_to_bytes('1GB') == 1024 ** 3
    assert manager.human_to_bytes('1TB') == 1024 ** 4
    assert manager.human_to_bytes('10.5GB') == int(10.5 * 1024 ** 3)
    
    # Test bytes to human
    assert manager.bytes_to_human(1024) == '1.0 KB'
    assert manager.bytes_to_human(1024 ** 2) == '1.0 MB'
    assert manager.bytes_to_human(1024 ** 3) == '1.0 GB'
    
    print("✓ Size conversion tests passed")


def test_list_partitions():
    """Test listing partitions."""
    print("\nTesting partition listing...")
    manager = PartitionManager()
    
    partitions = manager.list_partitions()
    assert isinstance(partitions, list)
    assert len(partitions) > 0
    
    # Check partition structure
    for partition in partitions:
        assert 'device' in partition
        assert 'size_human' in partition
        assert 'type' in partition
    
    print(f"✓ Found {len(partitions)} partitions")


def test_extend_partition():
    """Test extending a partition."""
    print("\nTesting partition extension...")
    manager = PartitionManager()
    manager.list_partitions()
    
    # Get first partition
    if manager.partitions:
        device = manager.partitions[0]['device']
        result = manager.extend_partition(device, '10GB', dry_run=True)
        
        assert result['success'] is True
        assert result['operation'] == 'extend'
        assert result['dry_run'] is True
        assert 'message' in result
        
        print(f"✓ Extend test passed for {device}")


def test_shrink_partition():
    """Test shrinking a partition."""
    print("\nTesting partition shrinking...")
    manager = PartitionManager()
    manager.list_partitions()
    
    # Get first partition
    if manager.partitions:
        device = manager.partitions[0]['device']
        result = manager.shrink_partition(device, '5GB', dry_run=True)
        
        assert result['success'] is True
        assert result['operation'] == 'shrink'
        assert result['dry_run'] is True
        assert 'message' in result
        
        print(f"✓ Shrink test passed for {device}")


def test_resize_partition():
    """Test resizing a partition."""
    print("\nTesting partition resizing...")
    manager = PartitionManager()
    manager.list_partitions()
    
    # Get first partition
    if manager.partitions:
        device = manager.partitions[0]['device']
        result = manager.resize_partition(device, '150GB', dry_run=True)
        
        assert result['success'] is True
        assert 'resize' in result['operation']
        assert result['dry_run'] is True
        assert 'message' in result
        
        print(f"✓ Resize test passed for {device}")


def test_partition_info():
    """Test getting partition info."""
    print("\nTesting partition info...")
    manager = PartitionManager()
    manager.list_partitions()
    
    # Get first partition
    if manager.partitions:
        device = manager.partitions[0]['device']
        info = manager.get_partition_info(device)
        
        assert info is not None
        assert info['device'] == device
        assert 'size_human' in info
        
        print(f"✓ Info test passed for {device}")


def test_free_space():
    """Test calculating free space."""
    print("\nTesting free space calculation...")
    manager = PartitionManager()
    manager.list_partitions()
    
    # Get first partition
    if manager.partitions:
        device = manager.partitions[0]['device']
        free_info = manager.calculate_free_space(device)
        
        assert free_info['success'] is True
        assert 'total_size' in free_info
        assert 'free_size' in free_info
        assert 'used_size' in free_info
        
        print(f"✓ Free space test passed for {device}")


def test_error_handling():
    """Test error handling."""
    print("\nTesting error handling...")
    manager = PartitionManager()
    
    # Test non-existent partition
    result = manager.extend_partition('/dev/nonexistent', '10GB')
    assert result['success'] is False
    assert 'error' in result
    
    # Test shrinking more than partition size
    manager.list_partitions()
    if manager.partitions:
        device = manager.partitions[0]['device']
        result = manager.shrink_partition(device, '1000TB')
        assert result['success'] is False
        assert 'error' in result
    
    print("✓ Error handling tests passed")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Partition Manager Test Suite")
    print("=" * 60)
    
    try:
        test_size_conversion()
        test_list_partitions()
        test_extend_partition()
        test_shrink_partition()
        test_resize_partition()
        test_partition_info()
        test_free_space()
        test_error_handling()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
