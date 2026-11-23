REASONS = {
    'EMPTY': '文件无内容', 'BLANK_FILE': '文件只有空白', 'HEADER_ONLY': '文件只有表头',
    'ENCODING': '无法识别编码', 'CSV': '表格语法错误', 'HEADER': '表头无效',
    'WIDTH': '列数与表头不一致', 'CONTRACT': '列契约无法应用', 'REQUIRED': '主键或业务字段缺失',
    'TIMESTAMP': '时间需包含偏移量', 'NUMBER': '数字无法归一', 'RANGE': '数字越界',
    'EXACT_DUP': '同版本重复传输', 'SUPERSEDED': '已被更新版本代替',
    'REV_CONFLICT': '最高版本证据有冲突', 'BUSINESS': '业务规则无法判定',
    'MISSING_BOOK': '外部账缺少业务键', 'MISSING_RESULT': '复算结果缺少业务键',
    'AMOUNT_DELTA': '复算与外部账计量不同', 'BOOK_CONFLICT': '独立账含重复业务键',
    'RUN_UNKNOWN': '没有此批次', 'DEMO_UNKNOWN': '没有此样例', 'STALE': '复核版本已过期',
    'REVIEW_NOTE': '有差异时须填写复核意见', 'REVIEW_DECISION': '复核结论无效',
    'RECEIPT_CONFLICT': '领料回单重复或内容冲突', 'RECEIPT_UNKNOWN': '没有此领料回单',
    'EVIDENCE_CONFLICT': '逐单凭据含重复业务键', 'EVIDENCE_SCOPE': '逐单凭据范围与回单不符',
    'EVIDENCE_TOTAL': '逐单凭据合计与回单不符', 'HANDOVER_BLOCKED': '当前凭据不足，禁止签认',
    'HANDOVER_SCOPE': '签认范围无效',
    'TOTAL_MATCH': '合单总额相符，各单待凭据', 'TOTAL_DELTA': '合单总额不符',
    'PENDING_EVIDENCE': '待仓库补齐逐单凭据', 'EVIDENCE_MATCH': '逐单差异已全部消除',
    'EVIDENCE_DELTA': '逐单凭据显示各单仍有差异',
}

REASONS.update({'CUT_FORMAT': '切件规格无效', 'CUT_LIMIT': '切件超限', 'CUT_SIZE': '切件超长或为空', 'CUT_REMAINDER': '余料长度异常', 'CUT_KERF': '锯缝不足', 'DATE': '日期格式无效', 'REV_BLOCKED': '较新来源尚未采信'})
