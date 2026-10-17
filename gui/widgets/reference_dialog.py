from pathlib import Path
from PySide6.QtWidgets import (QDialog,QFormLayout,QLineEdit,QPushButton,QDoubleSpinBox,
    QPlainTextEdit,QLabel,QFileDialog,QDialogButtonBox)


class ReferenceDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent); self.setWindowTitle("参考 RL 逐点对照（不自动更改验证状态）"); self.resize(650,450)
        form=QFormLayout(self)
        hint=QLabel("仅对照已计算网格的 RL；不插值、不外推，不把实测 S11 当作 RL。\n"
                    "参考 CSV 列：frequency_ghz、thickness_mm、rl_db；单位 GHz / mm / dB。")
        hint.setWordWrap(True); form.addRow(hint)
        self.file=QLineEdit(); form.addRow("参考 CSV",self.file)
        choose=QPushButton("选择参考文件…"); choose.clicked.connect(self.choose); form.addRow(choose)
        self.output=QLineEdit(str(parent.completed["directory"].parent/"reference_checks")); form.addRow("报告输出目录",self.output)
        output=QPushButton("选择输出目录…"); output.clicked.connect(self.choose_output); form.addRow(output)
        self.tolerance=QDoubleSpinBox(); self.tolerance.setDecimals(6); self.tolerance.setRange(0,100); self.tolerance.setValue(.05)
        form.addRow("允许绝对偏差 (dB)",self.tolerance)
        self.notes=QPlainTextEdit(); self.notes.setPlaceholderText("参考软件/版本、样品、模型、金属背板、虚部定义等；未确认条件请写明。")
        form.addRow("条件记录（必填）",self.notes)
        self.error=QLabel(); self.error.setWordWrap(True); form.addRow(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,"参考 RL 文件","","CSV (*.csv)")
        if path: self.file.setText(path)

    def choose_output(self):
        path=QFileDialog.getExistingDirectory(self,"报告目录",self.output.text())
        if path: self.output.setText(path)

    def values(self):
        return dict(reference=self.file.text().strip(),output=self.output.text().strip(),
                    notes=self.notes.toPlainText().strip(),tolerance_db=self.tolerance.value())

    def accept(self):
        value=self.values()
        if not Path(value["reference"]).is_file() or not value["output"] or not value["notes"]:
            self.error.setText("请选择参考文件、输出目录并填写条件记录。"); return
        super().accept()
