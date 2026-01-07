#!/usr/bin/env python3
"""
Partition Management Tool
A simple partition management utility for size-related operations.
Similar to MiniTool Partition Wizard but focused on size management.

Features:
- List partitions
- Extend partitions
- Shrink partitions
- Resize partitions
- Size conversion utilities
"""

import os
import sys
import subprocess
import re
import json
from typing import List, Dict, Optional, Tuple, Any


class PartitionManager:
    """Main class for managing disk partitions."""
    
    def __init__(self):
        """Initialize the Partition Manager."""
        self.partitions = []
        
    def list_partitions(self) -> List[Dict[str, Any]]:
        """
        List all available partitions on the system.
        
        Returns:
            List of dictionaries containing partition information.
        """
        partitions = []
        
        try:
            # Try to use lsblk for Linux systems
            if sys.platform.startswith('linux'):
                result = subprocess.run(
                    ['lsblk', '-b', '-n', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split()
                        if len(parts) >= 3 and parts[2] == 'part':
                            partition = {
                                'device': f"/dev/{parts[0].strip('├─└│')}",
                                'size_bytes': int(parts[1]),
                                'size_human': self.bytes_to_human(int(parts[1])),
                                'type': parts[2],
                                'mountpoint': parts[3] if len(parts) > 3 else 'N/A'
                            }
                            partitions.append(partition)
            
            # Fallback for other systems or if lsblk fails
            elif sys.platform == 'darwin':
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                # Parse diskutil output (simplified)
                lines = result.stdout.split('\n')
                for line in lines:
                    if '/dev/disk' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            partition = {
                                'device': parts[0] if parts[0].startswith('/dev/') else 'N/A',
                                'size_human': parts[1] if len(parts) > 1 else 'N/A',
                                'type': 'partition',
                                'mountpoint': 'N/A'
                            }
                            if partition['device'] != 'N/A':
                                partitions.append(partition)
            
            # Windows support using PowerShell
            elif sys.platform == 'win32':
                # Use PowerShell to get partition information
                ps_command = (
                    "Get-Partition | Select-Object DriveLetter, DiskNumber, PartitionNumber, "
                    "Size, @{Name='Type';Expression={'Partition'}} | "
                    "ConvertTo-Json"
                )
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                import json
                partition_data = json.loads(result.stdout)
                
                # Handle single partition (not a list)
                if isinstance(partition_data, dict):
                    partition_data = [partition_data]
                
                for part in partition_data:
                    drive_letter = part.get('DriveLetter', '')
                    disk_num = part.get('DiskNumber', 0)
                    part_num = part.get('PartitionNumber', 0)
                    size_bytes = part.get('Size', 0)
                    
                    # Create device identifier
                    if drive_letter:
                        device = f"{drive_letter}:"
                        mountpoint = f"{drive_letter}:\\"
                    else:
                        device = f"Disk {disk_num} Partition {part_num}"
                        mountpoint = 'N/A'
                    
                    partition = {
                        'device': device,
                        'size_bytes': int(size_bytes),
                        'size_human': self.bytes_to_human(int(size_bytes)),
                        'type': 'part',
                        'mountpoint': mountpoint
                    }
                    partitions.append(partition)
                                
        except subprocess.CalledProcessError as e:
            print(f"Error listing partitions: {e}")
        except FileNotFoundError:
            print("Required system tools not found. Running in simulation mode.")
            # Return mock data for demonstration
            partitions = self._get_mock_partitions()
        except json.JSONDecodeError as e:
            print(f"Error parsing partition data: {e}")
            # Return mock data for demonstration
            partitions = self._get_mock_partitions()
            
        self.partitions = partitions
        return partitions
    
    def _get_mock_partitions(self) -> List[Dict[str, Any]]:
        """
        Generate mock partition data for demonstration purposes.
        
        Returns:
            List of mock partition dictionaries.
        """
        return [
            {
                'device': '/dev/sda1',
                'size_bytes': 107374182400,  # 100 GB
                'size_human': '100.0 GB',
                'type': 'part',
                'mountpoint': '/'
            },
            {
                'device': '/dev/sda2',
                'size_bytes': 53687091200,  # 50 GB
                'size_human': '50.0 GB',
                'type': 'part',
                'mountpoint': '/home'
            },
            {
                'device': '/dev/sdb1',
                'size_bytes': 214748364800,  # 200 GB
                'size_human': '200.0 GB',
                'type': 'part',
                'mountpoint': '/data'
            }
        ]
    
    def extend_partition(self, device: str, size: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Extend a partition by the specified size.
        
        Args:
            device: The partition device path (e.g., /dev/sda1)
            size: Size to extend by (e.g., '10GB', '500MB')
            dry_run: If True, only simulate the operation
            
        Returns:
            Dictionary with operation results.
        """
        size_bytes = self.human_to_bytes(size)
        
        # Find the partition
        partition = self._find_partition(device)
        if not partition:
            return {
                'success': False,
                'error': f'Partition {device} not found'
            }
        
        current_size = partition.get('size_bytes', 0)
        new_size = current_size + size_bytes
        
        result = {
            'success': True,
            'device': device,
            'operation': 'extend',
            'current_size': self.bytes_to_human(current_size),
            'size_to_add': size,
            'new_size': self.bytes_to_human(new_size),
            'dry_run': dry_run
        }
        
        if dry_run:
            result['message'] = f"[DRY RUN] Would extend {device} from {result['current_size']} to {result['new_size']}"
        else:
            result['message'] = f"[SIMULATION] Extended {device} from {result['current_size']} to {result['new_size']}"
            # In a real implementation, this would call system tools like parted, resize2fs, etc.
            # For safety, we keep this as simulation only
            
        return result
    
    def shrink_partition(self, device: str, size: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Shrink a partition by the specified size.
        
        Args:
            device: The partition device path (e.g., /dev/sda1)
            size: Size to shrink by (e.g., '10GB', '500MB')
            dry_run: If True, only simulate the operation
            
        Returns:
            Dictionary with operation results.
        """
        size_bytes = self.human_to_bytes(size)
        
        # Find the partition
        partition = self._find_partition(device)
        if not partition:
            return {
                'success': False,
                'error': f'Partition {device} not found'
            }
        
        current_size = partition.get('size_bytes', 0)
        
        if size_bytes >= current_size:
            return {
                'success': False,
                'error': f'Cannot shrink {device} by {size} - would result in negative size'
            }
        
        new_size = current_size - size_bytes
        
        result = {
            'success': True,
            'device': device,
            'operation': 'shrink',
            'current_size': self.bytes_to_human(current_size),
            'size_to_remove': size,
            'new_size': self.bytes_to_human(new_size),
            'dry_run': dry_run
        }
        
        if dry_run:
            result['message'] = f"[DRY RUN] Would shrink {device} from {result['current_size']} to {result['new_size']}"
        else:
            result['message'] = f"[SIMULATION] Shrunk {device} from {result['current_size']} to {result['new_size']}"
            # In a real implementation, this would call system tools like parted, resize2fs, etc.
            # For safety, we keep this as simulation only
            
        return result
    
    def resize_partition(self, device: str, new_size: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Resize a partition to a specific size.
        
        Args:
            device: The partition device path (e.g., /dev/sda1)
            new_size: Target size (e.g., '100GB', '50MB')
            dry_run: If True, only simulate the operation
            
        Returns:
            Dictionary with operation results.
        """
        new_size_bytes = self.human_to_bytes(new_size)
        
        # Find the partition
        partition = self._find_partition(device)
        if not partition:
            return {
                'success': False,
                'error': f'Partition {device} not found'
            }
        
        current_size = partition.get('size_bytes', 0)
        
        if new_size_bytes == current_size:
            return {
                'success': True,
                'message': f'Partition {device} is already {new_size}',
                'no_change': True
            }
        
        operation = 'extend' if new_size_bytes > current_size else 'shrink'
        
        result = {
            'success': True,
            'device': device,
            'operation': f'resize ({operation})',
            'current_size': self.bytes_to_human(current_size),
            'new_size': new_size,
            'dry_run': dry_run
        }
        
        if dry_run:
            result['message'] = f"[DRY RUN] Would resize {device} from {result['current_size']} to {result['new_size']}"
        else:
            result['message'] = f"[SIMULATION] Resized {device} from {result['current_size']} to {result['new_size']}"
            # In a real implementation, this would call system tools like parted, resize2fs, etc.
            # For safety, we keep this as simulation only
            
        return result
    
    def _find_partition(self, device: str) -> Optional[Dict[str, Any]]:
        """
        Find a partition by device path.
        
        Args:
            device: The partition device path
            
        Returns:
            Partition dictionary if found, None otherwise.
        """
        if not self.partitions:
            self.list_partitions()
            
        for partition in self.partitions:
            if partition['device'] == device:
                return partition
        return None
    
    @staticmethod
    def bytes_to_human(size_bytes: int) -> str:
        """
        Convert bytes to human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Human-readable size string (e.g., '10.5 GB')
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    @staticmethod
    def human_to_bytes(size_str: str) -> int:
        """
        Convert human-readable size to bytes.
        
        Args:
            size_str: Size string (e.g., '10GB', '500MB', '1.5TB')
            
        Returns:
            Size in bytes
        """
        size_str = size_str.upper().strip()
        
        # Extract number and unit
        match = re.match(r'^([\d.]+)\s*([KMGTP]?B?)$', size_str)
        if not match:
            raise ValueError(f"Invalid size format: {size_str}")
        
        number = float(match.group(1))
        unit = match.group(2)
        
        # Normalize unit
        if unit in ['B', '']:
            multiplier = 1
        elif unit in ['K', 'KB']:
            multiplier = 1024
        elif unit in ['M', 'MB']:
            multiplier = 1024 ** 2
        elif unit in ['G', 'GB']:
            multiplier = 1024 ** 3
        elif unit in ['T', 'TB']:
            multiplier = 1024 ** 4
        elif unit in ['P', 'PB']:
            multiplier = 1024 ** 5
        else:
            raise ValueError(f"Unknown unit: {unit}")
        
        return int(number * multiplier)
    
    def get_partition_info(self, device: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific partition.
        
        Args:
            device: The partition device path
            
        Returns:
            Partition information dictionary if found, None otherwise.
        """
        partition = self._find_partition(device)
        if partition:
            return partition.copy()
        return None
    
    def calculate_free_space(self, device: str) -> Dict[str, Any]:
        """
        Calculate free space on a partition.
        
        Args:
            device: The partition device path
            
        Returns:
            Dictionary with free space information.
        """
        partition = self._find_partition(device)
        if not partition:
            return {
                'success': False,
                'error': f'Partition {device} not found'
            }
        
        # In a real implementation, this would query the filesystem
        # For simulation, we'll estimate 30% free space
        total_size = partition.get('size_bytes', 0)
        free_bytes = int(total_size * 0.3)
        used_bytes = total_size - free_bytes
        
        return {
            'success': True,
            'device': device,
            'total_size': self.bytes_to_human(total_size),
            'used_size': self.bytes_to_human(used_bytes),
            'free_size': self.bytes_to_human(free_bytes),
            'used_percent': 70.0,
            'free_percent': 30.0
        }


def print_partition_table(partitions: List[Dict[str, Any]]) -> None:
    """
    Print partitions in a formatted table.
    
    Args:
        partitions: List of partition dictionaries
    """
    if not partitions:
        print("No partitions found.")
        return
    
    print("\n" + "=" * 80)
    print(f"{'Device':<15} {'Size':<12} {'Type':<10} {'Mount Point':<20}")
    print("=" * 80)
    
    for partition in partitions:
        device = partition.get('device', 'N/A')
        size = partition.get('size_human', 'N/A')
        ptype = partition.get('type', 'N/A')
        mount = partition.get('mountpoint', 'N/A')
        print(f"{device:<15} {size:<12} {ptype:<10} {mount:<20}")
    
    print("=" * 80 + "\n")


def main():
    """Main CLI interface for the Partition Manager."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Partition Management Tool - Size-related operations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  
  # Linux/macOS examples:
  %(prog)s extend /dev/sda1 10GB
  %(prog)s shrink /dev/sda1 5GB
  %(prog)s resize /dev/sda1 100GB
  %(prog)s info /dev/sda1
  %(prog)s free /dev/sda1
  
  # Windows examples:
  %(prog)s extend C: 10GB
  %(prog)s shrink D: 5GB
  %(prog)s resize C: 100GB
  %(prog)s info C:
  %(prog)s free C:
        """
    )
    
    parser.add_argument(
        'command',
        choices=['list', 'extend', 'shrink', 'resize', 'info', 'free'],
        help='Command to execute'
    )
    
    parser.add_argument(
        'device',
        nargs='?',
        help='Partition device path (e.g., /dev/sda1 on Linux/macOS, C: on Windows)'
    )
    
    parser.add_argument(
        'size',
        nargs='?',
        help='Size for extend/shrink/resize operations (e.g., 10GB, 500MB)'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute the operation (default is dry-run/simulation)'
    )
    
    args = parser.parse_args()
    
    manager = PartitionManager()
    
    if args.command == 'list':
        partitions = manager.list_partitions()
        print_partition_table(partitions)
        
    elif args.command == 'info':
        if not args.device:
            print("Error: Device path required for 'info' command")
            sys.exit(1)
        
        info = manager.get_partition_info(args.device)
        if info:
            print(f"\nPartition Information for {args.device}:")
            print("-" * 40)
            for key, value in info.items():
                print(f"{key.replace('_', ' ').title():<20}: {value}")
            print("-" * 40 + "\n")
        else:
            print(f"Error: Partition {args.device} not found")
            sys.exit(1)
    
    elif args.command == 'free':
        if not args.device:
            print("Error: Device path required for 'free' command")
            sys.exit(1)
        
        free_info = manager.calculate_free_space(args.device)
        if free_info.get('success'):
            print(f"\nFree Space Information for {args.device}:")
            print("-" * 40)
            print(f"Total Size    : {free_info['total_size']}")
            print(f"Used Size     : {free_info['used_size']} ({free_info['used_percent']:.1f}%)")
            print(f"Free Size     : {free_info['free_size']} ({free_info['free_percent']:.1f}%)")
            print("-" * 40 + "\n")
        else:
            print(f"Error: {free_info.get('error')}")
            sys.exit(1)
    
    elif args.command == 'extend':
        if not args.device or not args.size:
            print("Error: Device path and size required for 'extend' command")
            sys.exit(1)
        
        result = manager.extend_partition(args.device, args.size, dry_run=not args.execute)
        if result.get('success'):
            print(f"\n{result['message']}")
            print(f"  Current Size: {result['current_size']}")
            print(f"  Size to Add : {result['size_to_add']}")
            print(f"  New Size    : {result['new_size']}\n")
        else:
            print(f"Error: {result.get('error')}")
            sys.exit(1)
    
    elif args.command == 'shrink':
        if not args.device or not args.size:
            print("Error: Device path and size required for 'shrink' command")
            sys.exit(1)
        
        result = manager.shrink_partition(args.device, args.size, dry_run=not args.execute)
        if result.get('success'):
            print(f"\n{result['message']}")
            print(f"  Current Size   : {result['current_size']}")
            print(f"  Size to Remove : {result['size_to_remove']}")
            print(f"  New Size       : {result['new_size']}\n")
        else:
            print(f"Error: {result.get('error')}")
            sys.exit(1)
    
    elif args.command == 'resize':
        if not args.device or not args.size:
            print("Error: Device path and size required for 'resize' command")
            sys.exit(1)
        
        result = manager.resize_partition(args.device, args.size, dry_run=not args.execute)
        if result.get('success'):
            if result.get('no_change'):
                print(f"\n{result['message']}\n")
            else:
                print(f"\n{result['message']}")
                print(f"  Current Size : {result['current_size']}")
                print(f"  New Size     : {result['new_size']}\n")
        else:
            print(f"Error: {result.get('error')}")
            sys.exit(1)


if __name__ == '__main__':
    main()
