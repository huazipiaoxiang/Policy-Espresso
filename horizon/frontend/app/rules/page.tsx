import { getSettings } from "@/lib/api";

export const dynamic = "force-dynamic";

// Agent 与规则配置（管理员视图）
export default async function RulesPage() {
  const settings = await getSettings();

  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
      <div className="mb-3 flex items-center gap-2">
        <h1 className="text-[16px] font-semibold">Agent 与规则</h1>
        <span className="text-[12px] text-[var(--text-3)]">
          分析管线配置 · 模型路由 · 规则引擎
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* LLM 模型分层 */}
        {settings && (
          <div className="card p-4">
            <div className="section-label mb-3">模型分层路由</div>
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
                <div>
                  <div className="text-[12px] font-medium text-[var(--text)]">分类 / 打标</div>
                  <div className="text-[11px] text-[var(--text-3)]">政策分类与主题标注</div>
                </div>
                <span className="font-mono text-[12px] text-[var(--accent)]">{settings.llm.model_tier.classify}</span>
              </div>
              <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
                <div>
                  <div className="text-[12px] font-medium text-[var(--text)]">结构化抽取</div>
                  <div className="text-[11px] text-[var(--text-3)]">金额、期限、义务提取</div>
                </div>
                <span className="font-mono text-[12px] text-[var(--accent)]">{settings.llm.model_tier.extract}</span>
              </div>
              <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
                <div>
                  <div className="text-[12px] font-medium text-[var(--text)]">影响分析</div>
                  <div className="text-[11px] text-[var(--text-3)]">业务影响评估</div>
                </div>
                <span className="font-mono text-[12px] text-[var(--accent)]">{settings.llm.model_tier.impact}</span>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[12px] font-medium text-[var(--text)]">Studio 建议书</div>
                  <div className="text-[11px] text-[var(--text-3)]">政策建议生成</div>
                </div>
                <span className="font-mono text-[12px] text-[var(--accent)]">{settings.llm.model_tier.studio}</span>
              </div>
            </div>
          </div>
        )}

        {/* LLM Provider 配置 */}
        {settings && (
          <div className="card p-4">
            <div className="section-label mb-3">LLM Provider</div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">Provider</span>
                <span className="font-mono text-[12px] text-[var(--text)]">{settings.llm.provider}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">百炼 Key</span>
                <span
                  className="text-[12px] font-medium"
                  style={{ color: settings.llm.dashscope_configured ? "var(--ok)" : "var(--danger)" }}
                >
                  {settings.llm.dashscope_configured ? "已配置" : "未配置"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">Ollama 端点</span>
                <span className="font-mono text-[11px] text-[var(--text-3)]">{settings.llm.ollama_base_url || "—"}</span>
              </div>
            </div>
          </div>
        )}

        {/* 规则引擎状态 */}
        <div className="card p-4">
          <div className="section-label mb-3">规则引擎</div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[12px] font-medium text-[var(--text)]">适用范围判定</div>
                <div className="text-[11px] text-[var(--text-3)]">规则通道 + LLM 通道双路判定</div>
              </div>
              <span className="rounded bg-[var(--ok)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--ok)]">
                运行中
              </span>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[12px] font-medium text-[var(--text)]">冲突检测</div>
                <div className="text-[11px] text-[var(--text-3)]">规则与 LLM 结果不一致时标记</div>
              </div>
              <span className="rounded bg-[var(--ok)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--ok)]">
                已启用
              </span>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[12px] font-medium text-[var(--text)]">相关性分级</div>
                <div className="text-[11px] text-[var(--text-3)]">High / Medium / Low 三级分流</div>
              </div>
              <span className="rounded bg-[var(--ok)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--ok)]">
                已启用
              </span>
            </div>
          </div>
        </div>

        {/* 分析管线流程 */}
        <div className="card p-4">
          <div className="section-label mb-3">分析管线流程</div>
          <div className="space-y-2 text-[12px]">
            <div className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white text-[10px] font-semibold">
                1
              </span>
              <div>
                <div className="font-medium text-[var(--text)]">文档抓取</div>
                <div className="text-[11px] text-[var(--text-3)]">从配置的数据源抓取政策文档</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white text-[10px] font-semibold">
                2
              </span>
              <div>
                <div className="font-medium text-[var(--text)]">相关性判定</div>
                <div className="text-[11px] text-[var(--text-3)]">规则 + LLM 双路判定 High/Medium/Low</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white text-[10px] font-semibold">
                3
              </span>
              <div>
                <div className="font-medium text-[var(--text)]">AI 深度分析</div>
                <div className="text-[11px] text-[var(--text-3)]">High 相关政策进入结构化抽取与影响评估</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white text-[10px] font-semibold">
                4
              </span>
              <div>
                <div className="font-medium text-[var(--text)]">人工审核</div>
                <div className="text-[11px] text-[var(--text-3)]">Medium 相关政策人工快速筛选</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white text-[10px] font-semibold">
                5
              </span>
              <div>
                <div className="font-medium text-[var(--text)]">发布分发</div>
                <div className="text-[11px] text-[var(--text-3)]">审核通过后发布到订阅渠道</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card mt-4 p-4">
        <div className="section-label mb-2">配置说明</div>
        <div className="text-[12px] text-[var(--text-3)] leading-relaxed">
          <p className="mb-2">
            <strong className="text-[var(--text-2)]">模型分层：</strong>
            不同分析阶段使用不同模型，平衡成本与效果。分类打标使用轻量模型，影响分析使用高级模型。
          </p>
          <p className="mb-2">
            <strong className="text-[var(--text-2)]">规则引擎：</strong>
            通过正则匹配快速判定政策适用范围，与 LLM 判定结果交叉验证。冲突时标记供人工复核。
          </p>
          <p>
            <strong className="text-[var(--text-2)]">配置方式：</strong>
            运行期配置由环境变量注入（.env 文件），修改后需重启后端服务生效。
          </p>
        </div>
      </div>
    </main>
  );
}
