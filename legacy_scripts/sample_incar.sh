#!/bin/bash

# 目标目录路径
TARGET_DIR="./incar_smp"  # 请修改为实际的目标路径
PROBABILITY=1  # 复制概率，例如0.5表示50%的概率
MAX_COUNT=1000    # 最大复制数量

# 检查目标目录是否存在，不存在则创建
mkdir -p "$TARGET_DIR"

# 计数器
count=0

# 遍历当前目录下的所有INCAR文件
for incar_file in $(find ./katze/ -name "INCAR" -type f); do
    # 如果已经达到最大数量，停止循环
    if [ $count -ge $MAX_COUNT ]; then
        echo "已达到最大复制数量 $MAX_COUNT，停止复制"
        break
    fi
    
    # 生成0-1之间的随机数
    random_value=$(awk -v seed=$RANDOM 'BEGIN{srand(seed); print rand()}')
    
    # 如果随机数小于等于概率值，则复制文件
    if (( $(echo "$random_value <= $PROBABILITY" | bc -l) )); then
        # 生成目标文件名（添加计数以避免覆盖）
        target_file="${TARGET_DIR}/INCAR_${count}"
        
        # 复制文件
        cp "$incar_file" "$target_file"
        
        # 增加计数器
        ((count++))
        
        echo "已复制: $incar_file -> $target_file (计数: $count/$MAX_COUNT)"
    fi
done

echo "复制完成！总共复制了 $count 个文件到 $TARGET_DIR"
