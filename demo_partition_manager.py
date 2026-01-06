#!/usr/bin/env python3
"""
Demo script for Partition Management Tool
Shows various capabilities of the tool
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from partition_manager import PartitionManager, print_partition_table


def print_header(title):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def demo_list_partitions():
    """Demo: List all partitions."""
    print_header("DEMO 1: List All Partitions")
    
    manager = PartitionManager()
    partitions = manager.list_partitions()
    print_partition_table(partitions)


def demo_partition_info():
    """Demo: Get detailed partition information."""
    print_header("DEMO 2: Get Partition Information")
    
    manager = PartitionManager()
    manager.list_partitions()
    
    if manager.partitions:
        device = manager.partitions[0]['device']
        info = manager.get_partition_info(device)
        
        print(f"Detailed information for {device}:")
        print("-" * 40)
        for key, value in info.items():
            print(f"  {key.replace('_', ' ').title():<18}: {value}")
        print("-" * 40)


def demo_free_space():
    """Demo: Check free space."""
    print_header("DEMO 3: Check Free Space")
    
    manager = PartitionManager()
    manager.list_partitions()
    
    if manager.partitions:
        for partition in manager.partitions[:2]:  # Show first 2
            device = partition['device']
            free_info = manager.calculate_free_space(device)
            
            if free_info.get('success'):
                print(f"Free space on {device}:")
                print(f"  Total: {free_info['total_size']}")
                print(f"  Used:  {free_info['used_size']} ({free_info['used_percent']:.1f}%)")
                print(f"  Free:  {free_info['free_size']} ({free_info['free_percent']:.1f}%)")
                print()


def demo_extend():
    """Demo: Extend partition."""
    print_header("DEMO 4: Extend Partition")
    
    manager = PartitionManager()
    manager.list_partitions()
    
    if manager.partitions:
        device = manager.partitions[0]['device']
        
        print(f"Extending {device} by 20GB (dry run):")
        result = manager.extend_partition(device, '20GB', dry_run=True)
        
        if result.get('success'):
            print(f"  ✓ {result['message']}")
            print(f"  Current: {result['current_size']}")
            print(f"  To Add:  {result['size_to_add']}")
            print(f"  Result:  {result['new_size']}")


def demo_shrink():
    """Demo: Shrink partition."""
    print_header("DEMO 5: Shrink Partition")
    
    manager = PartitionManager()
    manager.list_partitions()
    
    if manager.partitions:
        device = manager.partitions[0]['device']
        
        print(f"Shrinking {device} by 10GB (dry run):")
        result = manager.shrink_partition(device, '10GB', dry_run=True)
        
        if result.get('success'):
            print(f"  ✓ {result['message']}")
            print(f"  Current:   {result['current_size']}")
            print(f"  To Remove: {result['size_to_remove']}")
            print(f"  Result:    {result['new_size']}")


def demo_resize():
    """Demo: Resize partition."""
    print_header("DEMO 6: Resize Partition to Specific Size")
    
    manager = PartitionManager()
    manager.list_partitions()
    
    if manager.partitions:
        device = manager.partitions[0]['device']
        
        print(f"Resizing {device} to 200GB (dry run):")
        result = manager.resize_partition(device, '200GB', dry_run=True)
        
        if result.get('success'):
            print(f"  ✓ {result['message']}")
            print(f"  Current: {result['current_size']}")
            print(f"  Target:  {result['new_size']}")


def demo_size_conversions():
    """Demo: Size conversion utilities."""
    print_header("DEMO 7: Size Conversion Utilities")
    
    manager = PartitionManager()
    
    print("Converting human-readable sizes to bytes:")
    sizes = ['1KB', '10MB', '5.5GB', '1TB']
    for size in sizes:
        bytes_val = manager.human_to_bytes(size)
        print(f"  {size:>8} = {bytes_val:>15,} bytes")
    
    print("\nConverting bytes to human-readable format:")
    byte_vals = [1024, 1048576, 1073741824, 1099511627776]
    for bytes_val in byte_vals:
        human = manager.bytes_to_human(bytes_val)
        print(f"  {bytes_val:>15,} bytes = {human:>10}")


def demo_error_handling():
    """Demo: Error handling."""
    print_header("DEMO 8: Error Handling")
    
    manager = PartitionManager()
    
    print("Testing error handling scenarios:")
    
    # Non-existent partition
    print("\n1. Trying to extend non-existent partition:")
    result = manager.extend_partition('/dev/nonexistent', '10GB')
    if not result.get('success'):
        print(f"   ✓ Correctly caught error: {result.get('error')}")
    
    # Shrinking too much
    manager.list_partitions()
    if manager.partitions:
        device = manager.partitions[0]['device']
        print(f"\n2. Trying to shrink {device} by 1000TB (more than partition size):")
        result = manager.shrink_partition(device, '1000TB')
        if not result.get('success'):
            print(f"   ✓ Correctly caught error: {result.get('error')}")


def main():
    """Run all demos."""
    print("\n" + "=" * 80)
    print("  PARTITION MANAGEMENT TOOL - DEMONSTRATION")
    print("=" * 80)
    
    try:
        demo_list_partitions()
        demo_partition_info()
        demo_free_space()
        demo_extend()
        demo_shrink()
        demo_resize()
        demo_size_conversions()
        demo_error_handling()
        
        print("\n" + "=" * 80)
        print("  END OF DEMONSTRATION")
        print("=" * 80 + "\n")
        
        print("Note: All partition modification operations shown above are DRY RUNS.")
        print("The tool runs in safe simulation mode and does not modify actual partitions.\n")
        
    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
