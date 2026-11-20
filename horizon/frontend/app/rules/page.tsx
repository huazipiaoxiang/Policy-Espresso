const LEGAL_ENTITIES = [
  { name: "汇丰银行（中国）有限公司", code: "HSBC-CN", markets: "中国内地", status: "适用", policies: 42 },
  { name: "汇丰银行（香港）", code: "HSBC-HK", markets: "香港", status: "适用", policies: 38 },
  { name: "汇丰银行（新加坡）", code: "HSBC-SG", markets: "新加坡", status: "适用", policies: 25 },
  { name: "汇丰银行（英国）", code: "HSBC-UK", markets: "英国", status: "适用", policies: 31 },
  { name: "恒生银行", code: "HASE-HK", markets: "香港", status: "部分适用", policies: 18 },
];

const RULE_ENGINE_ITEMS = [
  {
    name: "适用范围判定",
    description: "规则通道 + LLM 通道双路判定政策对法人实体的适用性",
    status: "运行中",
    statusType: "green" as const,
  },
  {
    name: "冲突检测",
    description: "规则与 LLM 结果不一致时自动标记，提交人工复核",
    status: "已启用",
    statusType: "green" as const,
  },
  {
    name: "相关性分级",
    description: "判定政策对汇丰（香港 / 内地）实体的相关性：High / Medium / Low / 未提及",
    status: "已启用",
    statusType: "green" as const,
  },
  {
    name: "模型分层路由",
    description: "分类 / 规划 → qwen-flash，抽取 / 适用范围 → qwen-plus，影响分析 / 政策建议 → qwen-max",
    status: "已配置",
    statusType: "green" as const,
  },
  {
    name: "附件解析",
    description: "PDF / HTML 文档自动解析，OCR 识别扫描件，最大 20 个附件/文档",
    status: "已启用",
    statusType: "green" as const,
  },
];

const PIPELINE_STEPS = [
  { step: 1, name: "文档抓取", desc: "数据源抓取 → URL 去重 → 内容清洗 → 变更检测 → gate-1 过滤入库" },
  { step: 2, name: "P1 分类", desc: "判定是否金融政策，非金融或低置信文档直接跳过分析" },
  { step: 3, name: "P2 结构化抽取", desc: "抽取发文机构、文号、主题、条款等字段与可定位证据片段" },
  { step: 4, name: "P3 适用范围", desc: "规则 + LLM 双通道判定汇丰实体适用性，冲突标记人工复核" },
  { step: 5, name: "P4 影响分析", desc: "案例匹配 + 业务图谱 + 暴露聚合 → 8 维评分卡出优先级" },
  { step: 6, name: "P5 预警草稿", desc: "生成六段预警，结构校验失败时降级为保底文案" },
  { step: 7, name: "发布决策", desc: "判定明确时由 AI 直接发布；低置信结论仅在内部分析页留痕，不再进入人工流转" },
];

export default function RulesPage() {
  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">AGENT & RULES</div>
          <h1>Agent 与规则</h1>
          <p className="sub">分析管线配置 · 模型路由 · 规则引擎</p>
        </div>
      </div>

      <div className="twocol">
        <section className="panel">
          <div className="panelhead">
            <h2>法人实体适用性</h2>
            <small>{LEGAL_ENTITIES.length} 个实体</small>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>实体名称</th>
                  <th>市场</th>
                  <th>状态</th>
                  <th>相关政策</th>
                </tr>
              </thead>
              <tbody>
                {LEGAL_ENTITIES.map((entity) => (
                  <tr key={entity.code}>
                    <td>
                      <div className="policytitle">
                        {entity.name}
                        <small>{entity.code}</small>
                      </div>
                    </td>
                    <td style={{ fontSize: "12px" }}>{entity.markets}</td>
                    <td>
                      <span className={`badge ${entity.status === "适用" ? "green" : "amber"}`}>
                        {entity.status}
                      </span>
                    </td>
                    <td style={{ fontSize: "12px", fontFamily: "monospace" }}>{entity.policies}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="panelhead">
            <h2>规则引擎</h2>
            <small>5 项规则</small>
          </div>
          <div className="sectionbody">
            {RULE_ENGINE_ITEMS.map((item) => (
              <div className="rule-item" key={item.name}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>{item.name}</b>
                  <span className={`badge ${item.statusType}`}>{item.status}</span>
                </div>
                <p>{item.description}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: "18px" }}>
        <div className="panelhead">
          <h2>分析管线流程</h2>
          <small>7 个阶段</small>
        </div>
        <div className="sectionbody">
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {PIPELINE_STEPS.map((p) => (
              <div key={p.step} className="task">
                <div className="number">{String(p.step).padStart(2, "0")}</div>
                <div className="taskinfo">
                  <strong>{p.name}</strong>
                  <small>{p.desc}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel" style={{ marginTop: "18px" }}>
        <div className="panelhead">
          <h2>LLM Provider 配置</h2>
        </div>
        <div className="sectionbody">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "17px" }}>
            <div className="field">
              <small>Provider</small>
              <strong>dashscope</strong>
            </div>
            <div className="field">
              <small>百炼 Key</small>
              <strong style={{ color: "var(--green)" }}>已配置</strong>
            </div>
            <div className="field">
              <small>Ollama 端点</small>
              <strong style={{ fontFamily: "monospace", fontSize: "12px" }}>http://localhost:11434</strong>
            </div>
            <div className="field">
              <small>分类 / 规划模型</small>
              <strong style={{ fontFamily: "monospace", fontSize: "12px" }}>qwen-flash</strong>
            </div>
            <div className="field">
              <small>抽取 / 适用范围模型</small>
              <strong style={{ fontFamily: "monospace", fontSize: "12px" }}>qwen-plus</strong>
            </div>
            <div className="field">
              <small>影响分析 / 政策建议模型</small>
              <strong style={{ fontFamily: "monospace", fontSize: "12px" }}>qwen-max</strong>
            </div>
          </div>
        </div>
      </section>

      <div className="info" style={{ marginTop: "18px" }}>
        <strong>配置说明：</strong>
        模型分层 — 不同分析阶段使用不同模型，平衡成本与效果。分类打标使用轻量模型，影响分析使用高级模型。
        规则引擎 — 通过正则匹配快速判定政策适用范围，与 LLM 判定结果交叉验证。冲突时标记供人工复核。
        运行期配置由环境变量注入（.env 文件），修改后需重启后端服务生效。
      </div>

      <p className="footnote">Agent 与规则配置为合成 Demo 数据。实际模型与参数由环境变量注入，运行期不可热改。</p>
    </main>
  );
}
