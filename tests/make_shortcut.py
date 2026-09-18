"""יוצר סמל אימוג'י, סמל לתיקייה וקיצור דרך להפעלת התוכנה בלי חלון טרמינל."""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = r"C:\Users\יהודה\פרויקטים\סמלי תיקיות"
os.makedirs(ICONS, exist_ok=True)
ico = os.path.join(ICONS, "זיהוי פנים.ico")

img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
font = ImageFont.truetype(r"C:\Windows\Fonts\seguiemj.ttf", 200)
ImageDraw.Draw(img).text((128, 128), "🧑", font=font, anchor="mm", embedded_color=True)
d = ImageDraw.Draw(img)
for (x, y, dx, dy) in ((14, 14, 1, 1), (242, 14, -1, 1), (14, 242, 1, -1), (242, 242, -1, -1)):
    d.line([(x, y), (x + dx * 60, y)], fill=(14, 165, 233, 255), width=16)
    d.line([(x, y), (x, y + dy * 60)], fill=(14, 165, 233, 255), width=16)
img.save(ico, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])

ini = os.path.join(ROOT, "desktop.ini")
if os.path.exists(ini):
    subprocess.run(["attrib", "-h", "-s", ini])
with open(ini, "w", encoding="utf-16") as f:
    f.write(f"[.ShellClassInfo]\r\nIconResource={ico},0\r\n")
subprocess.run(["attrib", "+h", "+s", ini])
subprocess.run(["attrib", "+r", ROOT])

pyw = r"C:\Users\יהודה\AppData\Local\Programs\Python\Python312\pythonw.exe"
targets = [os.path.join(ROOT, "זיהוי פנים.lnk")]
if os.path.isdir(r"C:\Users\יהודה\Desktop\קיצורים"):
    targets.append(r"C:\Users\יהודה\Desktop\קיצורים\זיהוי פנים.lnk")
for lnk in targets:
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');$s.TargetPath='{pyw}';"
          f"$s.Arguments='\"{os.path.join(ROOT, 'main.py')}\"';$s.WorkingDirectory='{ROOT}';$s.IconLocation='{ico},0';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print("created", lnk)
