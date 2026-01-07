# Partition Management Tool - Quick Examples

## Platform-Specific Examples

### Windows 11

#### 1. Check what partitions are available
```bash
python partition_manager.py list
```

Output:
```
================================================================================
Device          Size         Type       Mount Point         
================================================================================
C:              250.0 GB     part       C:\                 
D:              500.0 GB     part       D:\                 
================================================================================
```

#### 2. Get detailed info about a specific partition
```bash
python partition_manager.py info C:
```

#### 3. Check how much free space is on a partition
```bash
python partition_manager.py free C:
```

#### 4. Plan to extend a partition (dry run)
```bash
python partition_manager.py extend C: 20GB
```

This shows what WOULD happen without actually doing it (safe mode).

#### 5. Plan to shrink a partition (dry run)
```bash
python partition_manager.py shrink C: 10GB
```

#### 6. Plan to resize to a specific size (dry run)
```bash
python partition_manager.py resize C: 100GB
```

### Linux/macOS

#### 1. Check what partitions are available
```bash
python3 partition_manager.py list
```

Output:
```
================================================================================
Device          Size         Type       Mount Point         
================================================================================
/dev/sda1       74.0 GB      part       /                   
/dev/sda15      106.0 MB     part       /boot/efi           
/dev/sdb1       75.0 GB      part       /mnt                
================================================================================
```

#### 2. Get detailed info about a specific partition
```bash
python3 partition_manager.py info /dev/sda1
```

#### 3. Check how much free space is on a partition
```bash
python3 partition_manager.py free /dev/sda1
```

#### 4. Plan to extend a partition (dry run)
```bash
python3 partition_manager.py extend /dev/sda1 20GB
```

This shows what WOULD happen without actually doing it (safe mode).

#### 5. Plan to shrink a partition (dry run)
```bash
python3 partition_manager.py shrink /dev/sda1 10GB
```

#### 6. Plan to resize to a specific size (dry run)
```bash
python3 partition_manager.py resize /dev/sda1 100GB
```

## Supported Size Formats

- Bytes: `1024`, `2048B`
- Kilobytes: `10KB` or `10K`
- Megabytes: `500MB` or `500M`
- Gigabytes: `10GB` or `10G`
- Terabytes: `1TB` or `1T`
- Decimals: `10.5GB`, `1.5TB`

## Running the Demo

**Windows 11:**
```bash
python demo_partition_manager.py
```

**Linux/macOS:**
```bash
python3 demo_partition_manager.py
```

## Running Tests

**Windows 11:**
```bash
python test_partition_manager.py
```

**Linux/macOS:**
```bash
python3 test_partition_manager.py
```

## Important Notes

- **All operations are DRY RUNS by default** - they show what would happen without actually modifying partitions
- The tool is designed for **learning and planning** purposes
- For actual partition modifications, use professional tools like GParted, parted, or MiniTool Partition Wizard
- Always backup your data before modifying partitions with any tool
