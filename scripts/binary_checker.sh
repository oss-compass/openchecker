#!/bin/bash

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
        unzip -qq -P "" "$1" -d "$temp_dir"
    elif [[ $file_type == application/x-tar ]]; then
        tar -xf "$1" -C "$temp_dir"
    elif [[ $file_type == application/gzip ]]; then
        gunzip -c "$1" > "$temp_dir/temp_file"
        if [[ -f "$temp_dir/temp_file" ]]; then
            local inner_file_type=$(file --mime-type -b "$temp_dir/temp_file")
            if [[ $inner_file_type == application/x-tar ]]; then
                tar -xf "$temp_dir/temp_file" -C "$temp_dir"
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
        bunzip2 -c "$1" > "$temp_dir/temp_file"
        if [[ -f "$temp_dir/temp_file" ]]; then
            local inner_file_type=$(file --mime-type -b "$temp_dir/temp_file")
            if [[ $inner_file_type == application/x-tar ]]; then
                tar -xf "$temp_dir/temp_file" -C "$temp_dir"
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
# $1 = 仓库 URL，$2 = 由 get_project_dir_name 派生的目录名（owner__repo），
# 与 constans.py 中 download-checkout 创建的目录一致；basename 会在
# 不同 owner 的同名仓库间碰撞（复用别人的目录，扫错代码）
project_name="${2:-$(basename "$1" | sed 's/\.git$//')}"
if [ ! -e "$project_name" ]; then
    GIT_ASKPASS=/bin/true git clone --depth=1 "$1" "$project_name" > /dev/null 2>&1
fi

for file in $(find $project_name -type f -not -path '*/.git/*' -not -path '*/test/*')
do
    if [ ! -e "$file" ]; then
        continue
    fi

    local file_type=$(file --mime-type -b "$1")
    if [[ $file_type == application/zip || $file_type == application/x-tar || $file_type == application/gzip || $file_type == application/x-bzip2 ]]; then
        if check_compressed_binary "$file"; then
            echo "Binary archive found: $file"
        fi
    elif is_binary "$file"; then
        echo "Binary file found: $file"
    fi
done
# rm -rf $project_name
