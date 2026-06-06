r"""
UE4 Pak Reader - reads .pak file directory structure

Usage:
    python tools/read_pak.py
"""
import struct
import sys
import os


def read_pak_index(pak_path):
    """读取 pak 文件的目录索引"""
    with open(pak_path, 'rb') as f:
        # 读取文件大小
        f.seek(0, 2)
        file_size = f.tell()

        # UE4 pak 文件末尾有 Magic Number 和版本信息
        # Magic: 0x5A6F12E1
        # 从末尾往前搜索

        # 先尝试读取末尾的 pak footer
        # UE4 pak footer 结构:
        # int32 EncryptionKeyGuid (16 bytes)
        # uint8 Encrypted (1 byte)
        # int32 Magic (4 bytes) = 0x5A6F12E1
        # int32 Version (4 bytes)
        # int64 IndexOffset (8 bytes)
        # int64 IndexSize (4 bytes)
        # string IndexHash (20 bytes SHA1)

        # 尝试不同版本的 footer 大小
        for footer_size in [44, 48, 52, 56]:
            f.seek(file_size - footer_size)
            data = f.read(footer_size)

            # 搜索 magic number
            magic = struct.pack('<I', 0x5A6F12E1)
            pos = data.find(magic)
            if pos >= 0:
                # 找到了 magic
                offset = file_size - footer_size + pos
                f.seek(offset)
                magic_val = struct.unpack('<I', f.read(4))[0]
                version = struct.unpack('<I', f.read(4))[0]
                index_offset = struct.unpack('<Q', f.read(8))[0]
                index_size = struct.unpack('<I', f.read(4))[0]

                print(f"  Magic: 0x{magic_val:08X}")
                print(f"  Version: {version}")
                print(f"  Index Offset: {index_offset}")
                print(f"  Index Size: {index_size}")

                # 读取索引
                f.seek(index_offset)
                return read_index_entries(f, version)

        # 如果没找到 footer，尝试直接读取头部
        f.seek(0)
        magic = struct.unpack('<I', f.read(4))[0]
        if magic == 0x5A6F12E1:
            version = struct.unpack('<I', f.read(4))[0]
            print(f"  Header Magic: 0x{magic:08X}")
            print(f"  Version: {version}")

        return []


def read_index_entries(f, version):
    """读取索引条目"""
    entries = []

    try:
        # 读取 mount point
        mount_point_len = struct.unpack('<i', f.read(4))[0]
        if mount_point_len > 0 and mount_point_len < 1000:
            mount_point = f.read(mount_point_len).decode('utf-8', errors='replace')
        else:
            mount_point = ""

        # 读取条目数量
        entry_count = struct.unpack('<I', f.read(4))[0]
        print(f"  Mount Point: {mount_point}")
        print(f"  Entry Count: {entry_count}")

        if entry_count > 100000:
            print("  条目数过多，可能是加密或格式不同")
            return []

        # 读取每个条目
        for i in range(min(entry_count, 1000)):  # 限制最多读 1000 个
            # 文件名
            name_len = struct.unpack('<i', f.read(4))[0]
            if name_len <= 0 or name_len > 1000:
                break
            name = f.read(name_len).decode('utf-8', errors='replace')

            # 跳过其他字段（offset, size, hash 等）
            if version >= 8:
                f.read(32)  # offset(8) + size(8) + hash(16)
            else:
                f.read(24)  # offset(8) + size(8) + hash(8)

            entries.append(name)

        return entries
    except Exception as e:
        print(f"  读取索引失败: {e}")
        return []


def find_map_files(entries):
    """从条目列表中找到地图相关文件"""
    map_keywords = ['map', 'terrain', 'landscape', 'world', 'mini', 'level',
                    '地图', '地形', '场景', '大地图', '小地图']

    results = []
    for entry in entries:
        entry_lower = entry.lower()
        for keyword in map_keywords:
            if keyword in entry_lower:
                results.append(entry)
                break

    return results


def main():
    pak_dir = "D:\\洛克王国：世界(2002304)\\Win64\\NRC\\Content\\Paks"

    # 获取所有 pak 文件
    pak_files = []
    for f in os.listdir(pak_dir):
        if f.endswith('.pak') and not f.endswith('_P.pak'):
            pak_files.append(os.path.join(pak_dir, f))

    # 按大小排序，先检查小文件
    pak_files.sort(key=lambda x: os.path.getsize(x))

    print(f"找到 {len(pak_files)} 个 pak 文件\n")

    all_map_files = []

    for pak_path in pak_files:
        size_mb = os.path.getsize(pak_path) / 1024 / 1024
        if size_mb < 1:  # 跳过太小的文件
            continue

        print(f"\n=== {os.path.basename(pak_path)} ({size_mb:.1f} MB) ===")
        entries = read_pak_index(pak_path)

        if entries:
            map_files = find_map_files(entries)
            if map_files:
                print(f"  找到 {len(map_files)} 个地图相关文件:")
                for mf in map_files[:20]:
                    print(f"    {mf}")
                all_map_files.extend(map_files)
            else:
                print(f"  未找到地图相关文件（共 {len(entries)} 个条目）")
        else:
            print("  无法读取索引（可能加密）")

    print(f"\n\n=== 总结 ===")
    print(f"共找到 {len(all_map_files)} 个地图相关文件")
    for mf in all_map_files:
        print(f"  {mf}")


if __name__ == "__main__":
    main()
