#!/bin/bash

# 单个压缩包解压后允许落盘的最大字节数。
# 本脚本处理的是被扫描仓库（不可信来源）中的压缩文件，gzip/zip/tar 炸弹
# （如 <1MB 的 gz 解压出 GB 级内容）会在解压期间占满共享存储（repos_dir
# 位于 NFS），使同盘上其它 agent 的写入全部失败。ulimit -f 以 1024 字节
# 块为单位（bash 内建行为），超限时内核以 SIGXFSZ 终止写入进程。
MAX_EXTRACT_BYTES=268435456
MAX_EXTRACT_BLOCKS=$((MAX_EXTRACT_BYTES / 1024))
# 条目数上限：海量小文件的炸弹不触发单文件大小限制，但会耗尽 inode/
# 拖慢遍历（zipquine 类嵌套炸弹的外层也可能包含海量条目）
MAX_ARCHIVE_ENTRIES=10000

# Function to check if a file is binary
is_binary() {
    if [[ $(file --mime-type -b "$1") == application* || $(file --mime-type -b "$1") == image* || $(file --mime-type -b "$1") == audio* || $(file --mime-type -b "$1") == video* ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check if a compressed file contains binary files
check_compressed_binary() {
    local temp_dir=$(mktemp -d)
    local file_type=$(file --mime-type -b "$1")

    if [[ $file_type == application/zip ]]; then
        if [ "$(unzip -Z1 "$1" 2>/dev/null | wc -l)" -gt "$MAX_ARCHIVE_ENTRIES" ]; then
            echo "Archive entry count exceeds limit ($MAX_ARCHIVE_ENTRIES), skipping: $1"
            rm -rf "$temp_dir"
            return 1
        fi
        ( ulimit -f "$MAX_EXTRACT_BLOCKS"; unzip -qq -P "" "$1" -d "$temp_dir" )
    elif [[ $file_type == application/x-tar ]]; then
        if [ "$(tar -tf "$1" 2>/dev/null | wc -l)" -gt "$MAX_ARCHIVE_ENTRIES" ]; then
            echo "Archive entry count exceeds limit ($MAX_ARCHIVE_ENTRIES), skipping: $1"
            rm -rf "$temp_dir"
            return 1
        fi
        ( ulimit -f "$MAX_EXTRACT_BLOCKS"; tar -xf "$1" -C "$temp_dir" )
    elif [[ $file_type == application/gzip ]]; then
        ( ulimit -f "$MAX_EXTRACT_BLOCKS"; gunzip -c "$1" > "$temp_dir/temp_file" )
        if [[ -f "$temp_dir/temp_file" ]]; then
            local inner_file_type=$(file --mime-type -b "$temp_dir/temp_file")
            if [[ $inner_file_type == application/x-tar ]]; then
                ( ulimit -f "$MAX_EXTRACT_BLOCKS"; tar -xf "$temp_dir/temp_file" -C "$temp_dir" )
            else
                echo "Unsupported inner file type of gzip: $inner_file_type"
                rm -rf "$temp_dir"
                return 1
            fi
        else
            echo "Error decompressing gzip file."
            rm -rf "$temp_dir"
            return 1
        fi
    elif [[ $file_type == application/x-bzip2 ]]; then
        ( ulimit -f "$MAX_EXTRACT_BLOCKS"; bunzip2 -c "$1" > "$temp_dir/temp_file" )
        if [[ -f "$temp_dir/temp_file" ]]; then
            local inner_file_type=$(file --mime-type -b "$temp_dir/temp_file")
            if [[ $inner_file_type == application/x-tar ]]; then
                ( ulimit -f "$MAX_EXTRACT_BLOCKS"; tar -xf "$temp_dir/temp_file" -C "$temp_dir" )
            else
                echo "Unsupported inner file type of bzip2: $inner_file_type"
                rm -rf "$temp_dir"
                return 1
            fi
        else
            echo "Error decompressing bzip2 file."
            rm -rf "$temp_dir"
            return 1
        fi
    else
        echo "Unsupported compressed file type: $file_type"
        return 1
    fi

    flag=1
    for local_file in $(find $temp_dir -type f -not -path '*/.git/*')
    do
        if is_binary "$local_file"; then
            # echo "Binary file found in $1: $(echo $local_file | cut -d'/' -f4-)"
            flag=0
        fi
    done

    rm -rf "$temp_dir"
    return $flag
}

# Main script
project_name=$(basename $1 | sed 's/\.git$//') > /dev/null
if [ ! -e "$project_name" ]; then
    GIT_ASKPASS=/bin/true git clone --depth=1 $1 > /dev/null 2>&1
fi

for file in $(find $project_name -type f -not -path '*/.git/*' -not -path '*/test/*')
do
    if [ ! -e "$file" ]; then
        continue
    fi

    # 用当前遍历的文件判断类型；此前误用 $1（脚本的位置参数，即仓库 URL），
    # 导致压缩包永远走不到 check_compressed_binary 分支
    file_type=$(file --mime-type -b "$file")
    if [[ $file_type == application/zip || $file_type == application/x-tar || $file_type == application/gzip || $file_type == application/x-bzip2 ]]; then
        if check_compressed_binary "$file"; then
            echo "Binary archive found: $file"
        fi
    elif is_binary "$file"; then
        echo "Binary file found: $file"
    fi
done
# rm -rf $project_name
