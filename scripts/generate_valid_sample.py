import pandas as pd
from pathlib import Path
from datetime import datetime

out = Path(__file__).resolve().parents[1] / 'database' / 'ValidSample.xlsx'

# Prepare 6 rows x 11 columns
rows = 10
cols = 11
# initialize with empty
data = [["" for _ in range(cols)] for _ in range(rows)]

# Put some metadata lines
data[0][0] = ""
data[1][0] = "DANH SÁCH THAY ĐỔI NGƯỜI LAO ĐỘNG"  # title
data[2][0] = "THE LIST OF VIETNAMESE EMPLOYEE JOIN SOCIAL, ..."

# Header row (index 4)
headers = [
    'STT\nNo',
    'Mã NV\nEmp ID',
    'Họ và tên\nFull Name',
    'Ngày vào\nJoin Date',
    'Ngày sinh\nBirth Date',
    'Sổ BHXH\nSocaial No',
    'BẮT ĐẦU THAM GIA BHXH TẠI HSV.\nSTART JOINING SOCIAL INS AT HSV.',
    'Giới tính\nSex',
    ' Tình trạng                              Status',
    'Mức lương mới            New Salary',
    'Tháng - Năm                     Month - Year',
]
for c, h in enumerate(headers):
    data[4][c] = h

# Put the Month/Year value at K5 (row index 4, col index 10)
# As a datetime so parsing recognizes it
data[4][10] = datetime(2026, 6, 1)

# Add one data row at index 5
row_data = [
    1,
    '00001',
    'Nguyen Van A',
    datetime(2020,1,15),
    datetime(1990,5,20),
    'BHXH001',
    datetime(2021,6,1),
    'M',
    'Active',
    15000000,
    '',
]
for c, val in enumerate(row_data):
    data[5][c] = val

# Write to Excel using pandas
df = pd.DataFrame(data)
with pd.ExcelWriter(out, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, header=False)

print('Wrote', out)
