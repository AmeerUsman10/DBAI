# Partition Management Tool

A simple and safe partition management utility focused on size-related operations. Similar to MiniTool Partition Wizard but streamlined for size management tasks.

## Features

- **List Partitions**: View all available partitions on your system
- **Extend Partitions**: Increase partition size by a specified amount
- **Shrink Partitions**: Decrease partition size by a specified amount
- **Resize Partitions**: Set partition to a specific size
- **Partition Info**: Get detailed information about a specific partition
- **Free Space**: Check available free space on partitions
- **Size Conversion**: Automatic conversion between human-readable sizes and bytes

## Installation

1. Make sure you have Python 3.6 or later installed:
   ```bash
   python3 --version
   ```

2. Make the script executable:
   ```bash
   chmod +x partition_manager.py
   ```

## Usage

### Basic Syntax

```bash
python3 partition_manager.py <command> [device] [size] [--execute]
```

### Commands

#### 1. List Partitions

Display all available partitions on your system:

```bash
python3 partition_manager.py list
```

**Example Output:**
```
================================================================================
Device          Size         Type       Mount Point         
================================================================================
/dev/sda1       100.0 GB     part       /                   
/dev/sda2       50.0 GB      part       /home               
/dev/sdb1       200.0 GB     part       /data               
================================================================================
```

#### 2. Get Partition Info

Get detailed information about a specific partition:

```bash
python3 partition_manager.py info /dev/sda1
```

**Example Output:**
```
Partition Information for /dev/sda1:
----------------------------------------
Device              : /dev/sda1
Size Bytes          : 107374182400
Size Human          : 100.0 GB
Type                : part
Mountpoint          : /
----------------------------------------
```

#### 3. Check Free Space

Check available free space on a partition:

```bash
python3 partition_manager.py free /dev/sda1
```

**Example Output:**
```
Free Space Information for /dev/sda1:
----------------------------------------
Total Size    : 100.0 GB
Used Size     : 70.0 GB (70.0%)
Free Size     : 30.0 GB (30.0%)
----------------------------------------
```

#### 4. Extend Partition

Increase partition size by a specified amount:

```bash
# Dry run (default - shows what would happen)
python3 partition_manager.py extend /dev/sda1 10GB

# Execute the operation (simulation mode for safety)
python3 partition_manager.py extend /dev/sda1 10GB --execute
```

**Example Output:**
```
[DRY RUN] Would extend /dev/sda1 from 100.0 GB to 110.0 GB
  Current Size: 100.0 GB
  Size to Add : 10GB
  New Size    : 110.0 GB
```

#### 5. Shrink Partition

Decrease partition size by a specified amount:

```bash
# Dry run (default - shows what would happen)
python3 partition_manager.py shrink /dev/sda1 5GB

# Execute the operation (simulation mode for safety)
python3 partition_manager.py shrink /dev/sda1 5GB --execute
```

**Example Output:**
```
[DRY RUN] Would shrink /dev/sda1 from 100.0 GB to 95.0 GB
  Current Size   : 100.0 GB
  Size to Remove : 5GB
  New Size       : 95.0 GB
```

#### 6. Resize Partition

Set partition to a specific size:

```bash
# Dry run (default - shows what would happen)
python3 partition_manager.py resize /dev/sda1 150GB

# Execute the operation (simulation mode for safety)
python3 partition_manager.py resize /dev/sda1 150GB --execute
```

**Example Output:**
```
[DRY RUN] Would resize /dev/sda1 from 100.0 GB to 150GB
  Current Size : 100.0 GB
  New Size     : 150GB
```

### Size Formats

The tool supports various size formats:

- **Bytes**: `1024`, `2048B`
- **Kilobytes**: `10KB`, `10K`
- **Megabytes**: `500MB`, `500M`
- **Gigabytes**: `10GB`, `10G`
- **Terabytes**: `1TB`, `1T`
- **Petabytes**: `1PB`, `1P`

You can also use decimal values:
- `10.5GB`
- `1.5TB`
- `500.25MB`

## Safety Features

**IMPORTANT**: This tool runs in **simulation mode** for safety. It will:

1. **Dry Run by Default**: All operations are dry runs unless `--execute` flag is used
2. **Simulation Mode**: Even with `--execute`, operations are simulated and don't modify actual partitions
3. **Validation**: Checks for invalid operations (e.g., shrinking to negative size)
4. **Mock Data**: If system tools are unavailable, uses mock data for demonstration

### Why Simulation Mode?

Partition operations are dangerous and can lead to data loss if done incorrectly. This tool is designed as a **safe learning and planning tool**. To actually modify partitions, you would need to:

1. Run the tool as root/administrator
2. Implement actual calls to system tools like `parted`, `resize2fs`, etc.
3. Add proper backup and safety checks
4. Test thoroughly in a safe environment

## Examples

### Example 1: Check Partitions and Plan Resize

```bash
# List all partitions
python3 partition_manager.py list

# Check free space on /dev/sda1
python3 partition_manager.py free /dev/sda1

# Plan to extend /dev/sda1 by 20GB
python3 partition_manager.py extend /dev/sda1 20GB
```

### Example 2: Multiple Operations Planning

```bash
# Get info on partition
python3 partition_manager.py info /dev/sdb1

# Plan to shrink it
python3 partition_manager.py shrink /dev/sdb1 50GB

# Plan to resize to exact size
python3 partition_manager.py resize /dev/sdb1 150GB
```

### Example 3: Using Different Size Units

```bash
# Extend by megabytes
python3 partition_manager.py extend /dev/sda1 512MB

# Shrink by gigabytes
python3 partition_manager.py shrink /dev/sda2 2.5GB

# Resize to terabytes
python3 partition_manager.py resize /dev/sdb1 1TB
```

## Platform Support

- **Linux**: Uses `lsblk` for partition detection
- **macOS**: Uses `diskutil` for partition detection
- **Windows**: Falls back to mock data (can be extended with platform-specific tools)
- **Other**: Uses mock data for demonstration

## API Usage

You can also use the tool as a Python module:

```python
from partition_manager import PartitionManager

# Create manager instance
manager = PartitionManager()

# List partitions
partitions = manager.list_partitions()
for partition in partitions:
    print(f"{partition['device']}: {partition['size_human']}")

# Get partition info
info = manager.get_partition_info('/dev/sda1')
print(f"Size: {info['size_human']}")

# Extend partition (dry run)
result = manager.extend_partition('/dev/sda1', '10GB', dry_run=True)
print(result['message'])

# Shrink partition (dry run)
result = manager.shrink_partition('/dev/sda1', '5GB', dry_run=True)
print(result['message'])

# Resize partition (dry run)
result = manager.resize_partition('/dev/sda1', '100GB', dry_run=True)
print(result['message'])

# Size conversion utilities
bytes_val = manager.human_to_bytes('10GB')
human_val = manager.bytes_to_human(10737418240)
```

## Help

Display help and usage information:

```bash
python3 partition_manager.py --help
```

## Limitations

1. **Simulation Only**: Does not actually modify partitions
2. **No Backup**: Does not create backups (would be required for real implementation)
3. **No Filesystem Checks**: Does not validate filesystem compatibility
4. **No Alignment**: Does not handle partition alignment requirements
5. **Limited Platform Support**: Best on Linux, limited on other platforms

## Future Enhancements

If this tool were to be extended for production use, consider adding:

- Actual partition modification capabilities (with extensive safety checks)
- Automatic backup before operations
- Filesystem resizing integration
- Partition alignment handling
- GUI interface
- Undo/rollback capabilities
- Better error handling and validation
- Support for more partition types and filesystems
- Integration with LVM and RAID

## License

This tool is provided as-is for educational and planning purposes.

## Warning

⚠️ **NEVER use untested partition tools on important data!** Always backup your data before attempting any partition operations with any tool. This tool is for learning and planning purposes only.
