#!/usr/bin/env python3
import sys
import os
import shutil
from pathlib import Path


def fix_list_format(content):
    """修复列表格式，确保【- 】开头的行前面要么是空行，要么是另一个列表项"""
    lines = content.split('\n')
    fixed_lines = []

    for i, line in enumerate(lines):
        current_line = line.strip()
        # 处理被日语引号包裹的表格行
        if current_line.startswith('- "| ') and current_line.endswith(' |" '):
            # 移除引号和列表符号，只保留表格内容
            table_content = current_line[4:-2].strip()  # 移除开头的 '- "' 和结尾的 '"'
            if table_content.startswith('| '):
                table_content = table_content[2:]  # 移除多余的开头空格和|
            if table_content.endswith(' |'):
                table_content = table_content[:-2]  # 移除多余的结尾空格和|
            cells = [cell.strip() for cell in table_content.split('|')]
            fixed_line = '| ' + ' | '.join(cells) + ' |'
            fixed_lines.append(fixed_line)
        elif current_line.startswith('- '):
            # 如果是第一行或者上一行是空行或者上一行也是列表项，则直接添加
            if (i == 0 or not fixed_lines or not fixed_lines[-1].strip() or fixed_lines[-1].strip().startswith('- ')):
                fixed_lines.append(line)
            else:
                # 否则，在当前行之前添加一个空行
                fixed_lines.append('')
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def should_process_line(line):
    """检查一行是否需要处理（只包含 - | : 空格这些字符且长度超过3）"""
    stripped_line = line.strip()
    if len(stripped_line) <= 3:
        return False
    return all(char in '-|: ' for char in stripped_line)


def remove_colons(line):
    """移除行中的冒号字符"""
    if should_process_line(line):
        return line.replace(':', '')
    return line


def should_remove_line(line):
    """检查一行是否应该被删除（只包含 - | 空格这些字符且长度超过3）"""
    stripped_line = line.strip()
    if len(stripped_line) <= 3:
        return False
    return all(char in '-| ' for char in stripped_line)


def should_remove_colons(line):
    """检查一行是否需要删除冒号（只包含 : - | 空格这些字符且长度超过3）"""
    stripped_line = line.strip()
    if len(stripped_line) <= 3:
        return False
    return all(char in ':-| ' for char in stripped_line)


def fix_markdown_table(content):
    """修复Markdown表格格式"""
    lines = content.split('\n')
    fixed_lines = []
    table_lines = []
    in_table = False
    header_line = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 如果行满足条件，删除冒号
        if should_remove_colons(line):
            line = line.replace(':', '')

        # 检测表格行（以 | 开头且包含至少一个 | 的行）
        is_table_row = line.startswith('|') and '|' in line[1:]

        # 如果是表格行且应该被删除，则跳过
        if is_table_row and should_remove_line(line):
            i += 1
            continue

        # 如果是表格行
        if is_table_row:
            if not in_table:
                # 新表格开始
                if table_lines:
                    # 处理并添加之前的表格
                    fixed_lines.extend(process_table_lines(table_lines))
                    fixed_lines.append('')
                table_lines = []
                header_line = None
                in_table = True

            # 清理并添加表格行
            cells = [cell.strip() for cell in line.split('|')]
            cells = [cell for cell in cells if cell]  # 移除空的首尾单元格

            # 跳过分隔行
            if all(cell.replace('-', '') == '' for cell in cells):
                i += 1
                continue

            # 如果还没有表头，这一行就是表头
            if header_line is None:
                header_line = cells
            else:
                table_lines.append(cells)
        else:
            if in_table:
                # 表格结束，处理并添加表格
                if header_line and table_lines:
                    # 添加表头
                    fixed_lines.append('| ' + ' | '.join(header_line) + ' |')
                    # 添加分隔行
                    fixed_lines.append('|' + '|'.join(['---' for _ in header_line]) + '|')
                    # 添加数据行
                    for row in table_lines:
                        fixed_lines.append('| ' + ' | '.join(row) + ' |')
                    fixed_lines.append('')
                elif table_lines:  # 如果没有表头但有数据
                    fixed_lines.extend(process_table_lines(table_lines))
                    fixed_lines.append('')
                table_lines = []
                header_line = None
                in_table = False
            # 添加非表格行
            if line or (not line and fixed_lines and fixed_lines[-1]):
                fixed_lines.append(line)
        i += 1

    # 处理最后一个表格（如果有）
    if header_line and table_lines:
        # 添加表头
        fixed_lines.append('| ' + ' | '.join(header_line) + ' |')
        # 添加分隔行
        fixed_lines.append('|' + '|'.join(['---' for _ in header_line]) + '|')
        # 添加数据行
        for row in table_lines:
            fixed_lines.append('| ' + ' | '.join(row) + ' |')
    elif table_lines:  # 如果没有表头但有数据
        fixed_lines.extend(process_table_lines(table_lines))

    return '\n'.join(fixed_lines)


def process_table_lines(table_lines):
    """处理表格行并返回格式化的表格"""
    if not table_lines:
        return []

    formatted_lines = []
    # 添加表头
    formatted_lines.append('| ' + ' | '.join(table_lines[0]) + ' |')
    # 添加分隔行
    formatted_lines.append('|' + '|'.join(['---' for _ in table_lines[0]]) + '|')
    # 添加数据行
    for row in table_lines[1:]:
        formatted_lines.append('| ' + ' | '.join(row) + ' |')

    return formatted_lines


def needs_fixing(content):
    """检查内容是否需要修复"""
    lines = content.split('\n')
    in_table = False
    table_lines = []
    needs_fix = False

    for line in lines:
        line = line.strip()
        if line.startswith('|') and '|' in line[1:]:
            if not in_table:
                if table_lines:
                    # 如果之前的表格没有正确处理就开始新表格，说明需要修复
                    needs_fix = True
                    break
                in_table = True
            cells = [cell.strip() for cell in line.split('|')]
            cells = [cell for cell in cells if cell]
            if not all(cell.replace('-', '') == '' for cell in cells):
                table_lines.append(cells)
        else:
            if in_table:
                # 检查表格格式是否正确
                if len(table_lines) < 2:  # 至少需要表头和一行数据
                    needs_fix = True
                    break
                # 重置状态
                table_lines = []
                in_table = False

    # 检查最后一个表格
    if in_table and len(table_lines) < 2:
        needs_fix = True

    return needs_fix


def process_file(input_file):
    """处理单个Markdown文件"""
    try:
        # 读取文件
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 创建备份
        backup_file = str(input_file) + '.bak'
        shutil.copy2(input_file, backup_file)
        print(f"已创建备份: {backup_file}")

        # 修复内容
        fixed_content = fix_markdown_table(content)
        fixed_content = fix_list_format(fixed_content)

        # 写回文件
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

        print(f"成功修复文件: {input_file}")
        return True
    except Exception as e:
        print(f"处理文件 {input_file} 时出错: {str(e)}")
        return False


def process_directory(directory):
    """处理目录中的所有Markdown文件"""
    success_count = 0
    for md_file in Path(directory).rglob('*.md'):
        if process_file(md_file):
            success_count += 1
    return success_count


def main():
    if len(sys.argv) < 2:
        print("使用方法: python fix_markdown_tables.py <markdown_file_or_directory> [markdown_file_or_directory2 ...]")
        sys.exit(1)

    success_count = 0
    for path in sys.argv[1:]:
        if os.path.isdir(path):
            print(f"\n处理目录: {path}")
            success_count += process_directory(path)
        elif os.path.isfile(path):
            if not path.endswith('.md'):
                print(f"跳过非Markdown文件: {path}")
                continue
            if process_file(path):
                success_count += 1
        else:
            print(f"路径不存在: {path}")

    print(f"\n处理完成! 成功修复 {success_count} 个文件。")


if __name__ == "__main__":
    main()
