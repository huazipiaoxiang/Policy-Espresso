const SETTINGS_SECTIONS = [
  {
    title: "数据环境",
    items: [
      {
        label: "运行环境",
        value: "production",
        description: "当前运行环境，影响数据源抓取频率与日志级别",
      },
      {
        label: "数据库",
        value: "PostgreSQL 15.4",
        description: "主数据库连接，存储政策、文档、审计日志",
        status: "green",
      },
      {
        label: "存储后端",
        value: "Local + OSS",
        description: "本地文件系统 + 阿里云 OSS 对象存储",
      },
      {
        label: "时区",
        value: "Asia/Hong_Kong (UTC+8)",
        description: "系统全局时区，影响日志时间戳与调度",
      },
    ],
  },
  {
    title: "角色与权限",
    items: [
      {
        label: "鉴权方式",
        value: "X-API-Key（单用户）",
        description: "当前使用 API Key 鉴权，正式版需接入 SSO / RBAC",
      },
      {
        label: "审核角色",
        value: "Reviewer A / B / C",
        description: "三个人工审核角色，按业务线分配任务",
      },
      {
        label: "管理员",
        value: "Admin",
        description: "系统管理员，可配置数据源、规则引擎与发布",
      },
      {
        label: "FC 定时触发令牌",
        value: "已配置",
        description: "函数计算定时触发器使用的安全令牌",
        status: "green",
      },
    ],
  },
  {
    title: "通知服务",
    items: [
      {
        label: "站内通知",
        value: "已启用",
        description: "系统内消息通知，审核任务与异常告警",
        status: "green",
      },
      {
        label: "邮件 Webhook",
        value: "已配置",
        description: "SMTP 邮件发送，用于政策发布通知",
        status: "green",
      },
      {
        label: "企业微信 Webhook",
        value: "已配置",
        description: "企业微信群机器人，实时推送审核任务",
        status: "green",
      },
      {
        label: "飞书 Webhook",
        value: "未配置",
        description: "飞书群机器人，可选的通知渠道",
        status: "red",
      },
    ],
  },
];

const TECH_CONFIG = [
  { label: "LLM Provider", value: "dashscope" },
  { label: "分类 / 打标模型", value: "qwen-turbo" },
  { label: "结构化抽取模型", value: "qwen-plus" },
  { label: "影响分析模型", value: "qwen-max" },
  { label: "Studio 建议书模型", value: "qwen-max" },
  { label: "百炼 Key", value: "已配置", status: "green" },
  { label: "Ollama 端点", value: "http://localhost:11434" },
];

const CRAWL_CONFIG = [
  { label: "User-Agent", value: "PolicyEspresso-Bot/0.8" },
  { label: "每域限速", value: "2 req/s" },
  { label: "遵守 robots.txt", value: "是" },
  { label: "每文档附件上限", value: "20" },
  { label: "单源单轮条数上限", value: "不限制" },
];

export default function SettingsPage() {
  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">SYSTEM SETTINGS</div>
          <h1>系统设置</h1>
          <p className="sub">只读系统状态与配置快照 · 运行期配置由环境变量注入，需改 .env 后重启生效</p>
        </div>
      </div>

      {SETTINGS_SECTIONS.map((section) => (
        <section className="panel" key={section.title} style={{ marginTop: section === SETTINGS_SECTIONS[0] ? "18px" : "18px" }}>
          <div className="panelhead">
            <h2>{section.title}</h2>
          </div>
          <div className="sectionbody">
            {section.items.map((item) => (
              <div className="rule-item" key={item.label}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>{item.label}</b>
                  {item.status ? (
                    <span className={`badge ${item.status}`}>{item.value}</span>
                  ) : (
                    <span style={{ fontSize: "12px", fontFamily: "monospace", color: "#363a42" }}>{item.value}</span>
                  )}
                </div>
                <p>{item.description}</p>
              </div>
            ))}
          </div>
        </section>
      ))}

      <div className="twocol">
        <section className="panel">
          <div className="panelhead">
            <h2>模型分层路由</h2>
            <small>LLM 配置</small>
          </div>
          <div className="sectionbody">
            {TECH_CONFIG.map((cfg) => (
              <div className="rule-item" key={cfg.label}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>{cfg.label}</b>
                  {cfg.status ? (
                    <span className={`badge ${cfg.status}`}>{cfg.value}</span>
                  ) : (
                    <span style={{ fontSize: "12px", fontFamily: "monospace" }}>{cfg.value}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panelhead">
            <h2>抓取合规</h2>
            <small>Crawler 配置</small>
          </div>
          <div className="sectionbody">
            {CRAWL_CONFIG.map((cfg) => (
              <div className="rule-item" key={cfg.label}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>{cfg.label}</b>
                  <span style={{ fontSize: "12px", fontFamily: "monospace" }}>{cfg.value}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="info" style={{ marginTop: "18px" }}>
        <strong>注意：</strong>
        以上配置均为只读快照。运行期配置由环境变量（.env 文件）注入，修改后需重启后端服务生效。
        如需调整数据源抓取频率、模型参数或通知通道，请联系系统管理员。
      </div>

      <p className="footnote">系统设置为合成 Demo 数据。实际部署时，鉴权方式应接入企业 SSO，角色权限应实现 RBAC 模型。</p>
    </main>
  );
}
