"""列映射选择及六行预览，不改变文件或推断虚部约定。"""
import json
from pathlib import Path
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QComboBox,QTableWidget,
    QTableWidgetItem,QDialogButtonBox,QPushButton,QFileDialog,QLabel)
from core.models import COLUMNS
from gui.controllers.import_controller import validate_template


def configure_mapping(page, panel):
    """文件读取在所属页面后台线程中执行，编辑完成后再重新导入。"""
    if page.busy: return
    path,_=QFileDialog.getOpenFileName(page,"选择用于映射的示例文件","","表格 (*.csv *.xlsx *.xls)")
    if not path: return
    try: initial=panel.parser_options()
    except ValueError: initial={}
    from gui.controllers.import_controller import preview_table
    def ready(table):
        dialog=MappingDialog(table,initial,page)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            value=dialog.values()
            panel.mapping.setText(json.dumps(value["column_map"],ensure_ascii=False))
            panel.unit.setCurrentText(value["frequency_unit"])
            panel.convention.setCurrentIndex(panel.convention.findData(value["imaginary_convention"]))
            page.message.emit("映射已应用；请重新导入文件或扫描目录以检查。")
    launch=getattr(page,"_launch",None) or page.launch
    launch(lambda p,c:preview_table(path),ready)


class MappingDialog(QDialog):
    def __init__(self, table, initial, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV / Excel 列映射与预览（第一工作表）")
        self.resize(800,520)
        layout=QVBoxLayout(self); form=QFormLayout(); self.fields={}
        for name in COLUMNS:
            box=QComboBox(); box.addItem("请选择源列", "")
            for col in table.columns:
                box.addItem(col,col)
            wanted=initial.get("column_map",{}).get(name,name)
            box.setCurrentIndex(max(0,box.findData(wanted)))
            self.fields[name]=box; form.addRow(name,box)
        self.unit=QComboBox(); self.unit.addItems(["GHz","MHz","kHz","Hz"])
        self.unit.setCurrentText(initial.get("frequency_unit","GHz")); form.addRow("频率单位",self.unit)
        self.convention=QComboBox(); self.convention.addItems(["loss","signed"])
        self.convention.setCurrentText(initial.get("imaginary_convention","loss")); form.addRow("虚部解释（仍待外部验证）",self.convention)
        layout.addLayout(form)
        preview=QTableWidget(len(table),len(table.columns)); preview.setHorizontalHeaderLabels(list(table.columns))
        preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i,row in enumerate(table.itertuples(index=False,name=None)):
            for j,value in enumerate(row): preview.setItem(i,j,QTableWidgetItem(str(value)))
        layout.addWidget(preview)
        for title,callback in (("保存导入模板…",self.save_template),("读取导入模板…",self.load_template)):
            button=QPushButton(title); button.clicked.connect(callback); layout.addWidget(button)
        self.error=QLabel(); self.error.setWordWrap(True); layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def values(self):
        return validate_template(dict(column_map={k:v.currentData() for k,v in self.fields.items()},
            frequency_unit=self.unit.currentText(),imaginary_convention=self.convention.currentText()))

    def accept(self):
        try: self.values()
        except ValueError as error: self.error.setText(str(error)); return
        super().accept()

    def save_template(self):
        try:
            value=self.values()
            path,_=QFileDialog.getSaveFileName(self,"保存模板","import-template.json","JSON (*.json)")
            if path: Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
        except (ValueError,OSError) as error: self.error.setText(str(error))

    def load_template(self):
        path,_=QFileDialog.getOpenFileName(self,"读取模板","","JSON (*.json)")
        if not path: return
        try:
            value=validate_template(json.loads(Path(path).read_text(encoding="utf-8")))
            if any(self.fields[k].findData(v)<0 for k,v in value["column_map"].items()):
                raise ValueError("模板包含当前文件没有的源列。")
            for k,v in value["column_map"].items(): self.fields[k].setCurrentIndex(self.fields[k].findData(v))
            self.unit.setCurrentText(value["frequency_unit"]); self.convention.setCurrentText(value["imaginary_convention"])
        except (ValueError,OSError) as error: self.error.setText(str(error))
