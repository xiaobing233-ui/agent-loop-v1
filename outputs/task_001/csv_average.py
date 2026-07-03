#!/usr/bin/env python3
import csv
import sys


def parse_number(value):
    try:
        return float(value)
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python3 csv_average.py <csv文件路径> [列名]")
        sys.exit(1)

    csv_path = sys.argv[1]
    target_column = sys.argv[2] if len(sys.argv) >= 3 else None
    numbers = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            values = [row.get(target_column, "")] if target_column else row.values()
            for value in values:
                number = parse_number(str(value).strip())
                if number is not None:
                    numbers.append(number)

    if not numbers:
        print("没有找到可计算的数字")
        sys.exit(1)

    average = sum(numbers) / len(numbers)
    print(f"平均值: {average}")


if __name__ == "__main__":
    main()
