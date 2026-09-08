"""Build the deliberately fictional PDFs used by synthetic_corpus_v1."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "pdf"
PDF_DIR.mkdir(parents=True, exist_ok=True)

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
STYLES = getSampleStyleSheet()
TITLE = ParagraphStyle(
    "SyntheticTitle",
    parent=STYLES["Title"],
    fontName="STSong-Light",
    fontSize=18,
    leading=24,
    spaceAfter=14,
)
HEADING = ParagraphStyle(
    "SyntheticHeading",
    parent=STYLES["Heading2"],
    fontName="STSong-Light",
    fontSize=13,
    leading=18,
    spaceBefore=10,
    spaceAfter=7,
)
BODY = ParagraphStyle(
    "SyntheticBody",
    parent=STYLES["BodyText"],
    fontName="STSong-Light",
    fontSize=10.5,
    leading=18,
    spaceAfter=8,
)
SMALL = ParagraphStyle(
    "SyntheticSmall",
    parent=BODY,
    fontSize=8.5,
    leading=12,
    textColor=colors.HexColor("#555555"),
)


def header_footer(canvas, document):
    canvas.saveState()
    canvas.setFont("STSong-Light", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(2 * cm, 1.2 * cm, "Synthetic enterprise document - evaluation fixture only")
    canvas.drawRightString(19 * cm, 1.2 * cm, f"Page {document.page}")
    canvas.restoreState()


def build_text_pdf(filename: str, title: str, version: str, sections: list[tuple[str, list[str]]]):
    story = [
        Paragraph(title, TITLE),
        Paragraph(f"Document status: synthetic | Version: {version} | Evaluation fixture only", SMALL),
        Spacer(1, 5),
    ]
    for heading, paragraphs in sections:
        story.append(Paragraph(heading, HEADING))
        for text in paragraphs:
            story.append(Paragraph(text, BODY))
    SimpleDocTemplate(
        str(PDF_DIR / filename),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
        author="Enterprise Support Agent synthetic corpus",
    ).build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def build_table_pdf(filename: str, title: str, note: str, headers: list[str], rows: list[list[str]]):
    story = [Paragraph(title, TITLE), Paragraph(note, SMALL), Spacer(1, 8)]
    data = [[Paragraph(cell, SMALL) for cell in headers]]
    data.extend([[Paragraph(cell, SMALL) for cell in row] for row in rows])
    table = Table(data, colWidths=[3.0 * cm, 4.0 * cm, 3.2 * cm, 4.8 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C9D6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F6FAFC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Interpretation rule: this table is fabricated for parser and retrieval experiments. It must not be cited as a real company policy.", SMALL))
    SimpleDocTemplate(
        str(PDF_DIR / filename), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm, title=title,
    ).build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def build_scanned_pdf():
    width, height = 1654, 2339
    image = Image.new("RGB", (width, height), "#f6f0df")
    draw = ImageDraw.Draw(image)
    font_path = r"C:\\Windows\\Fonts\\msyh.ttc"
    title_font = ImageFont.truetype(font_path, 48)
    body_font = ImageFont.truetype(font_path, 30)
    small_font = ImageFont.truetype(font_path, 24)
    draw.rectangle((80, 80, width - 80, height - 80), outline="#5d564c", width=4)
    draw.text((160, 150), "访客访问登记表（扫描件模拟）", font=title_font, fill="#1d1d1d")
    draw.text((160, 230), "文件属性：synthetic / image-only / 用于 OCR 失败与低置信解析测试", font=small_font, fill="#444444")
    y = 350
    rows = [
        "访问日期：2026-09-01    访客姓名：王小明    被访部门：研发部",
        "证件类型：身份证（示例）    访问区域：3F 会议区    进入时间：09:30",
        "接待人：李四    临时权限：访客 Wi-Fi    离开时间：17:10",
        "安全提醒：访客不得进入机房、财务区或未授权办公区域。",
        "异常情况：证件遗失、陪同人离开或越权访问时，应立即联系前台与安全值班。",
    ]
    for row in rows:
        draw.rectangle((140, y, width - 140, y + 135), outline="#807766", width=2)
        draw.text((170, y + 42), row, font=body_font, fill="#222222")
        y += 150
    draw.line((160, y + 80, width - 160, y + 80), fill="#807766", width=2)
    draw.text((160, y + 120), "访客签名：____________________    接待人签名：____________________", font=body_font, fill="#222222")
    image_path = PDF_DIR / "visitor_access_registration_scan.png"
    image.save(image_path, "PNG")
    image.save(PDF_DIR / "visitor_access_registration_scan.pdf", "PDF", resolution=150.0)
    image_path.unlink()


def main():
    build_text_pdf(
        "remote_access_security_policy_v1.pdf",
        "远程访问安全规范", "v1.0",
        [
            ("适用范围", ["本规范适用于员工通过 VPN、远程桌面或受控浏览器访问内部系统的场景。所有远程访问必须使用企业账号和多因素认证。"]),
            ("访问控制", ["普通员工仅可访问岗位必需系统。管理员账户不得用于日常办公；管理员操作必须记录工单编号。", "远程会话闲置超过 30 分钟时，系统应自动断开。"]),
            ("事件处置", ["发现异常登录地点、重复 MFA 拒绝或疑似账号共享时，员工应在 1 小时内提交安全事件。"]),
        ],
    )
    build_text_pdf(
        "remote_access_security_policy_v2.pdf",
        "远程访问安全规范", "v2.0",
        [
            ("版本说明", ["v2.0 自 2026-10-01 起生效，并替代 v1.0。版本更新用于测试索引切换与来源版本展示。"]),
            ("访问控制", ["普通员工仅可访问岗位必需系统。管理员账户不得用于日常办公；管理员操作必须记录工单编号和变更审批号。", "远程会话闲置超过 15 分钟时，系统应自动断开。高风险系统访问必须从受管设备发起。"]),
            ("事件处置", ["发现异常登录地点、重复 MFA 拒绝或疑似账号共享时，员工应在 30 分钟内提交安全事件；安全团队应保留相关审计记录。"]),
        ],
    )
    build_text_pdf(
        "incident_response_handbook.pdf",
        "信息安全事件响应手册", "v1.0",
        [
            ("事件分级", ["P1：凭据泄露、生产系统不可用或大范围数据外泄风险。P2：单一业务系统异常且存在潜在扩大风险。P3：低影响配置或单用户安全咨询。"]),
            ("0 到 30 分钟", ["值班人员确认事件编号、受影响资产、发现时间和初始证据。禁止删除日志、重启关键服务器或擅自对外发布信息。"]),
            ("30 分钟到 4 小时", ["P1 必须通知安全负责人、业务负责人和法务联系人。处置人员按最小影响原则执行隔离，并持续记录每次操作的时间、操作者和结果。"]),
            ("恢复与复盘", ["服务恢复后 2 个工作日内完成根因分析。复盘必须区分直接原因、系统性原因和预防措施，并将需要长期跟踪的动作转为工单。"]),
        ],
    )
    build_table_pdf(
        "expense_approval_matrix.pdf", "费用审批矩阵", "Document status: synthetic | Version: 1.0", ["费用类型", "金额区间", "必需审批人", "补充材料"], [
            ["差旅住宿", "0 - 3000 元", "直属主管", "行程单、发票、支付凭证"],
            ["差旅住宿", "3001 - 8000 元", "直属主管 + 部门负责人", "行程单、发票、支付凭证、预算编号"],
            ["采购软件", "0 - 5000 元", "直属主管 + IT 资产管理员", "供应商报价、采购申请"],
            ["采购软件", "5001 元及以上", "直属主管 + 部门负责人 + 财务负责人", "供应商报价、采购申请、预算编号、合同摘要"],
            ["客户招待", "任意金额", "直属主管 + 财务负责人", "参与人员、业务事由、发票"],
        ])
    build_table_pdf(
        "network_change_window_calendar.pdf", "网络变更窗口日历", "Document status: synthetic | Version: 1.0", ["变更等级", "允许窗口", "审批要求", "回退要求"], [
            ["标准变更", "每周三 20:00 - 22:00", "网络负责人", "配置备份与 15 分钟回退步骤"],
            ["高风险变更", "每月第二个周六 22:00 - 02:00", "网络负责人 + 业务负责人 + 值班经理", "演练过的回退方案、现场值守"],
            ["紧急变更", "不限，但须事后 1 个工作日内补审", "值班经理口头批准后记录", "优先恢复业务，保留操作日志"],
            ["冻结期", "季度结算日前 3 个工作日", "禁止非紧急变更", "仅允许 P1 紧急修复"],
        ])
    build_scanned_pdf()


if __name__ == "__main__":
    main()
