# DBAI
MYSQL AI

## Partition Management Tool

This repository now includes a **Partition Management Tool** - a simple and safe utility for managing disk partitions with size-related operations.

### Features
- List all available partitions
- Extend partitions by a specified size
- Shrink partitions by a specified size
- Resize partitions to a specific size
- Get detailed partition information
- Check free space on partitions
- Size conversion utilities (GB, MB, TB, etc.)

### Quick Start

```bash
# List all partitions
python3 partition_manager.py list

# Get information about a specific partition
python3 partition_manager.py info /dev/sda1

# Extend a partition by 10GB (dry run)
python3 partition_manager.py extend /dev/sda1 10GB

# Shrink a partition by 5GB (dry run)
python3 partition_manager.py shrink /dev/sda1 5GB

# Resize a partition to 100GB (dry run)
python3 partition_manager.py resize /dev/sda1 100GB

# Check free space
python3 partition_manager.py free /dev/sda1
```

### Documentation

For complete documentation, usage examples, and API reference, see [PARTITION_MANAGER_README.md](PARTITION_MANAGER_README.md)

### Safety Notice

⚠️ The partition management tool runs in **simulation mode** for safety. It performs dry runs by default and does not modify actual partitions. This makes it safe for learning and planning purposes.
