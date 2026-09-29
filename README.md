# HalluGuard — 客服回复幻觉检测系统

> 任务 0110：对智能客服系统"说瞎话"的回复做批量幻觉检测，与人工标注（ground truth）对比计算漏检/误报，并给出误判归因。
>
> 技术栈：Python 3.13 + Flask + LangGraph + LangChain ｜ uv 包管理 ｜ Vue3 + Vite + Pinia ｜ pytest

---

## 1. 幻觉分类体系

ground truth 中的 9 种零散标签（政策编造/参数编造/能力越界/优惠编造/信息编造/政策偏差/安全误导/信息遗漏…）经 MECE 归纳收敛为 **5 类 × 3 级严重度**：

| 编号 | 类别 | 定义 | 严重度 | 覆盖 case |
|------|------|------|--------|-----------|
| C1 | 事实矛盾 | 回复断言与 KB **明确记载**直接冲突 | HIGH | h01 退货政策、h02 蓝牙版本、h04 纸质发票*、h06 材质/保修、h08 发货/快递、h17 充电接口 |
| C2 | 无据虚构 | 编造 KB **不存在或显式否认**的实体/入口/承诺 | HIGH | h05 优惠券、h07 退货地址、h09 NFC、h11 线下门店、h15 品牌关联、h19 学生优惠 |
| C3 | 能力越界 | 声称执行了系统**不具备的接口能力** | HIGH | h03 查物流、h10 查退款、h14 改地址、h18 升级工单 |
| C4 | 安全误导 | 健康/安全关键信息误导 | **CRITICAL** | h13 孕妇可用 |
| C5 | 信息遗漏 | 遗漏 KB 关键限定信息致建议失真 | LOW | h20 尺码反馈（边界模糊） |

\* h04 属"部分正确部分错误"（电子发票正确、纸质发票错误）→ 归 C1 但 `partial=true`，严重度降为 MEDIUM。

**关键边界设计**：
- C1 vs C2：KB 有明确记载且冲突 → C1；KB 无记载/显式否认而回复断言 → C2（如 h09"未标注 NFC"却肯定支持）。
- C5 是刻意压低置信度（0.55）的**模糊带**：遗漏≠编造，系统标记 `needs_review=true` 交人工复核，而非追求自动判对。
- 严重度排序依据业务风险：健康安全 > 资损/能力欺骗 > 一般事实错误 > 建议失真。

## 2. 检测方法

三层流水线，由 LangGraph 状态机编排（`backend/app/graph/workflow.py`）：

```
extract → rule_check（规则层） → llm_judge（裁判层） → reconcile（仲裁层）
```

### 2.1 规则层（`core/rules.py`）— 高精度确定性检查，零 LLM 成本

原则：**规则能确定性兜底的绝不过模型**。10 条规则包括：

- `capability_overreach`：KB 声明"未接入/不具备 XX 接口" + 回复出现"帮您查了/已修改/升级为"类能力声明词 → C3 确定性命中；
- `safety_misguidance`：KB 人群警示（孕妇建议咨询医生）+ 回复绿灯话术（放心使用）→ C4；
- `omission_absolute_claim`：KB 反馈统计（30% 用户反馈偏大）+ 回复绝对化断言（尺码标准不偏）→ C5（低置信进复核）；
- 结构化 C1/C2：优惠券/快递公司**集合成员校验**、"KB 显式否认 X + 回复肯定 X"（**否定前缀感知**，防止"不支持货到付款"因子串"支持货到付款"误报）、"纯线上 + 宣称线下店"、退货地址泄露等。

### 2.2 裁判层（`core/llm_judge.py`）— LLM-as-Judge，结构化 JSON 输出

- **real 模式**：OpenAI 兼容 API（DeepSeek 等），prompt 强制要求 evidence 必须引用 KB 原文片段、逐句校验、输出 partial 标志；**JSON 解析失败带错误上下文重试 1 次，仍失败则降级为仅规则结果**（`fallback=true`）；裁判给不出证据引用则判 NONE（防裁判自身幻觉）。
- **mock 模式**：确定性模拟裁判（覆盖政策天数/版本号/发货时长/材质/保修期冲突等语义模式），零外部依赖，保证离线可演示、CI 可回归。

### 2.3 仲裁层 — 结果融合

类型取并集、严重度取最高（客服幻觉的资损/信誉成本不对称，**宁可多报不漏报**）、置信度加权融合（规则层与裁判层**同类型交叉命中 → 独立证据源互证，置信度 +0.06**）、置信度 < 0.7 或显式模糊标记 → `needs_review=true`。

## 3. 检出率数据（mock 模式，20 条全量）

```
TP=18  FP=0  FN=0  TN=2
Precision=100.00%  Recall=100.00%  F1=100.00%  Accuracy=100.00%  分类对齐率=100.00%
```

| 类别 | 检出 | 示例证据 |
|------|------|----------|
| C1 事实矛盾 ×6 | 6/6 | h01：回复称「30天无理由」，KB 记载「7天无理由」 |
| C2 无据虚构 ×6 | 6/6 | h05：回复宣称满300减50，KB 活动仅含满200减20/满500减60 |
| C3 能力越界 ×4 | 4/4 | h03：KB 声明未接入物流查询接口，回复声称"帮您查了" |
| C4 安全误导 ×1 | 1/1 | h13：KB 警示孕妇建议咨询医生，回复称"孕妇可以放心使用" |
| C5 信息遗漏 ×1 | 1/1 | h20：检出但置信度 0.55，标记需人工复核 |
| 正常 ×2 | 2/2 放行 | h12/h16 无任何规则与裁判命中 |

产物：`backend/results/results.json`（逐条）、`backend/results/eval_report.json`（对比报告）。

## 4. 误判分析与易错 case

本数据集上无漏检/误报，但以下 case 是**设计中最容易误判**的地方，也是换数据集后的风险点：

| case | 易错点 | 本系统的处理 | 残余风险 |
|------|--------|--------------|----------|
| h20 信息遗漏 | GT 自己标注"边界较模糊"。LLM 裁判容易把它判成 C1 矛盾（过度敏感）或直接放行（漏检） | 规则层专设 C5 检查器，命中后置信度压到 0.55 进人工复核，**不参与自动化指标拔高** | 换数据集后绝对化断言模式（"尺码标准/不偏"）覆盖面有限 |
| h05 优惠券 | KB 里"**无**满300减50的活动"这句话本身含 `满300减50` 字样，朴素集合匹配会把 KB 的否认当成提供 → 漏检 | 优惠券规则先剔除 KB 显式否认的券（`无满X减Y的活动`）再做集合校验（开发中真实踩到并修掉的 bug，见测试 `test_e2e_dataset`） | 否认句式枚举不全时有漏检风险 |
| h04 部分正确 | 裁判倾向"全对或全错"，一刀切判幻觉会夸大错误 | 裁判层要求逐句校验输出 partial；规则层检测"回复同时肯定了 KB 支持的事项" → severity 降 MEDIUM | partial 判定依赖"支持X"模式抽取质量 |
| h09 NFC | "KB 未标注"≠"KB 否认"，但回复肯定支持就是幻觉；同时不能把"KB 未提及相关信息"的合理拒答误伤 | 显式否认（不支持）与未标注（未标注）分开建模：前者→C1，后者→C2 | "未标注"措辞在真实 KB 中变体多 |
| h12/h16 正常回复 | 否定前缀误报：h12 回复"**不**支持货到付款"含子串"支持货到付款" | `has_affirm` 做否定前缀感知（窗口 3 字符内出现 不/无/没/未/暂 等 → 判否定） | 否定表达变体（"并非""没有开通"）需持续扩充 |
| 通用风险 | **规则在本数据集上校准，存在过拟合风险**；20 条样本不足以证明泛化 | mock 模式诚实声明为"确定性模拟裁判"；real 模式由 LLM 裁判承担泛化职责；规则层与裁判层互为冗余 | 上线前需在更大规模真实样本上重测 P/R |

## 5. 快速开始

```bash
# 后端（backend/ 下）
uv sync                                   # 安装依赖
uv run pytest                             # 34 个测试（含 20 条全流程 e2e）
uv run python scripts/run_eval.py         # CLI 一键跑批 + 评测（产物写入 results/）
uv run python -m app.main                 # 启动 API（127.0.0.1:5001）

# 前端（frontend/ 下）
npm install
npm run dev                               # http://localhost:5175（/api 代理到 5001）
```

切换真实 LLM 裁判：复制 `backend/.env.example` → `.env`，设 `HALLU_MOCK=false` 并填 API Key。
`--mode real` 亦可临时覆盖（`uv run python scripts/run_eval.py --mode real`）。

### API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/health` | 健康检查（含裁判模式） |
| POST | `/api/detect` | 单条检测 `{user_question, system_reply, knowledge_base}` |
| POST | `/api/batch` | 20 条全量跑批（含原文对照字段） |
| GET | `/api/eval` | 对齐 ground truth → 指标 + 混淆矩阵 + 漏检/误报归因 |

## 6. AI 工具使用情况

- **开发方式**：全程与 AI 编码智能体（Trae · GLM）结对完成——需求拆解、分类体系设计讨论、代码生成、测试编写、跑批验证均由 AI 辅助，人工负责需求把关、架构决策与验收。
- **AI 产出占比**：代码与文档约 95% 由 AI 生成；人工主要做三件事：
  1. 定义分类体系的业务边界（C1/C2 划分标准、C5 模糊带的处理策略）；
  2. 审查规则层的防误报设计（否定前缀感知、KB 否认句式剔除）；
  3. 验收测试与评测数据（确认 h20 走人工复核而非硬判）。
- **AI 的典型错误与修正**：初版优惠券规则把 KB"无满300减50的活动"当成 KB 提供该券导致漏检 h05，由 e2e 测试捕获后修复——这类"KB 否认句式含实体字样"的坑也是真实业务中 LLM 裁判常见的失误模式。
- **借鉴**：三层流水线中的"仲裁层 + 置信度互证"参考了本人在法律咨询 RAG 项目（legalMind）中 Self-Reflection 质量门控的工程实践（评分阈值 + 一票否决 + 防无限循环重试）。

## 7. 项目结构

```
huanjue/
├── README.md  REQUIREMENTS.md  LICENSE  CHANGELOG.md  .github/workflows/ci.yml
├── data/                          # 任务数据（replies / ground_truth）
├── backend/
│   ├── pyproject.toml  .env.example  uv.lock
│   ├── app/
│   │   ├── main.py  config.py
│   │   ├── core/      taxonomy.py  rules.py  llm_judge.py  detector.py
│   │   ├── graph/     workflow.py            # LangGraph 状态机
│   │   ├── api/       routes.py              # Flask REST
│   │   └── services/  eval_service.py        # 指标 + 误判归因
│   ├── scripts/run_eval.py
│   ├── results/       results.json  eval_report.json
│   └── tests/         test_rules.py  test_judge_and_graph.py  test_eval.py  test_e2e_dataset.py
└── frontend/                      # Vue3 + Vite + Pinia（/detect 看板、/report 报告）
```

## 8. 后续优化路线

| 优先级 | 方向 | 做法 |
|--------|------|------|
| P0 | 规则泛化验证 | 扩充至数百条真实客服样本重测 P/R，规则只保留精确率 > 95% 的模式，其余移交裁判层 |
| P0 | real 模式并发与限流 | 批量 real 裁判接入 asyncio.Semaphore + 令牌桶限流（沿用 legalMind 的并发控制模式） |
| P1 | 证据定位升级 | 从"规则命中片段"升级为 token 级高亮（回复侧 spans + KB 侧 spans），前端对照渲染 |
| P1 | 裁判 ensemble | 双模型裁判 + 分歧样本进人工队列，降低单裁判偏差 |
| P2 | 检测左移 | 将本分类体系内嵌到客服生成侧（生成后 Self-Reflection 门控），把"检测"变"拦截" |
| P2 | 知识库结构化 | KB 参数抽成结构化字段（材质/保修/接口/政策），规则层从正则匹配升级为字段对比，彻底摆脱句式依赖 |
| P3 | 反馈闭环 | 人工复核结果回流为few-shot样例与规则回归用例，持续收敛误判率 |
