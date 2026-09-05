import type { Locale } from "@/i18n/config";

const en = {
  metadata: {
    defaultTitle: "TraFriend · Market analytics, clearly anchored",
    titleTemplate: "%s · TraFriend",
    description:
      "Single-day leveraged ETF scenarios and Profit Ratio analytics for U.S. markets.",
  },
  common: {
    english: "English",
    chinese: "中文",
    language: "Language",
    mockData: "Mock data",
    provider: "Provider",
    tradingDate: "Trading date",
  },
  header: {
    dashboardAria: "TraFriend dashboard",
    primaryNavigationAria: "Primary navigation",
    dashboard: "Dashboard",
    leverage: "Leverage",
    profitRatio: "Profit Ratio",
  },
  footer: {
    product: "TraFriend · Research tools for U.S. markets",
    disclosure: "Mock data only · Not investment advice",
  },
  apiStatus: {
    offline: "API offline",
    connected: "Mock API connected",
  },
  dashboard: {
    phase: "Phase 1 workspace",
    eyebrow: "Market analytics dashboard",
    headline: "Understand the relationship,",
    headlineMuted: " not just the quote.",
    intro:
      "Explore deterministic mock scenarios while TraFriend's data and calculation foundations are developed. No live provider is connected.",
    mode: "Mode",
    modeValue: "MOCK",
    storage: "Storage",
    storageValue: "MEMORY",
    availableNow: "Available now",
    toolkit: "Analytics toolkit",
    toolsOnline: "2 / 2 TOOLS ONLINE",
    openTool: "Open {title}",
    tools: {
      leverage: {
        eyebrow: "Scenario tool",
        title: "Leveraged ETF Calculator",
        description:
          "Translate a same-day target move between an underlying and its long or inverse leveraged ETF.",
      },
      profitRatio: {
        eyebrow: "Ownership signal",
        title: "Profit Ratio",
        description:
          "Inspect a mock estimate of profitable cost basis alongside daily closing prices.",
      },
    },
    dataPolicyAria: "Data policy",
    referenceTitle: "One reference. One trading day.",
    referenceDescription: "How calculator scenarios stay anchored",
    referenceSteps: [
      {
        title: "Capture",
        description:
          "A coherent pair is recorded at the configured overnight-session opening.",
      },
      {
        title: "Lock",
        description:
          "That immutable pair becomes the Daily Reference Price version.",
      },
      {
        title: "Calculate",
        description: "Every scenario for the day uses the same displayed anchor.",
      },
    ],
    foundationTitle: "Foundation status",
    foundationDescription: "Phase 1 boundaries",
    foundations: {
      mockProvider: "Deterministic mock provider",
      noCredentials: "No browser-side credentials",
      decimalCore: "Decimal-tested calculation core",
    },
  },
  leveragePage: {
    metadataTitle: "Leveraged ETF Calculator",
    metadataDescription:
      "Explore single-day leveraged ETF target-price relationships using mock reference data.",
    eyebrow: "Tools / Leverage",
    badge: "API-backed mock",
    title: "Leveraged ETF Calculator",
    description:
      "Move in either direction between a target underlying price and its theoretical leveraged ETF price.",
    warning:
      "Single-day theoretical relationship only. This is not a multi-day forecast.",
  },
  calculator: {
    genericError: "The mock API could not complete this request.",
    errors: {
      notFound: "The requested market-data resource was not found.",
      referenceChanged: "The Daily Reference Price changed. Please try again.",
      referenceUnavailable: "The Daily Reference Price is currently unavailable.",
      outOfDomain: "This target is outside the single-day model's valid price range.",
      validation: "Enter a valid positive target price.",
    },
    toolTitle: "Calculate leveraged target",
    toolDescription:
      "Calculate and display a same-day theoretical target using the currently selected mock relationship and Daily Reference Price.",
    invalidToolObject: "Expected an object with inputSide and targetPrice.",
    invalidToolInput: "inputSide or targetPrice is invalid.",
    relationship: "Relationship",
    selectProduct: "Select a leveraged product",
    mockReference: "Mock reference",
    pairLabel: "Underlying and ETF pair",
    pairPlaceholder: "Choose a pair",
    underlyingReference: "Underlying reference",
    etfReference: "{leverage} ETF reference",
    tradingDate: "Trading date {date}",
    provider: "Provider {provider}",
    calculateFrom: "Calculate from",
    targetTab: "{symbol} target",
    targetPrice: "{symbol} target price",
    referenceHelp:
      "The API calculates against reference version {version}; the browser never supplies the leverage factor.",
    calculating: "Calculating…",
    calculate: "Calculate theoretical price",
    output: "Output",
    resultTitle: "Theoretical same-day result",
    estimatedTarget: "Estimated target",
    dailyLeverage: "{leverage} daily",
    underlyingMove: "Underlying move",
    leveragedMove: "Leveraged move",
    singleDayWarning:
      "This estimate uses a single-day linear leverage relationship and is not a multi-day price forecast.",
    readyTitle: "Ready for a target price",
    readyDescription:
      "Select the direction, enter a target, and TraFriend will ask the mock API for the same-day theoretical relationship.",
  },
  profitRatioPage: {
    metadataTitle: "Profit Ratio",
    metadataDescription:
      "Inspect mock Profit Ratio history alongside stock closing prices.",
    eyebrow: "Tools / Profit Ratio",
    badge: "Mock methodology",
    title: "Profit Ratio",
    description:
      "Track the estimated share of profitable cost basis and compare its direction with price.",
    instrument: "Instrument",
  },
  profitRatio: {
    genericError: "The mock API could not load Profit Ratio data.",
    unavailableTitle: "Profit Ratio data is unavailable",
    emptySeries: "The mock series was empty.",
    profitRatio: "Profit Ratio",
    closingPrice: "Closing price",
    chartAria:
      "Seven-day chart comparing mock Profit Ratio and NVDA closing price",
    chartBadge: "1D · MOCK",
    currentEstimate: "Current estimate",
    final: "Final",
    sampleChange: "{value} percentage points in this sample",
    observed: "Observed {date}",
    methodology: "{provider} · methodology v{version}",
    historicalComparison: "Historical comparison",
    ratioVsPrice: "Ratio vs. closing price",
    accessibleView: "Accessible data view",
    mockObservations: "Mock observations",
    date: "Date",
    nvdaClose: "NVDA close",
    quality: "Quality",
    methodologyName: "Mock Profitable Cost Basis Ratio",
    disclosure:
      "{methodology}. Profit Ratio is methodology-dependent; this Phase 1 series is deterministic mock data and is not suitable for investment decisions.",
  },
};

export type Dictionary = typeof en;

const zhCN: Dictionary = {
  metadata: {
    defaultTitle: "TraFriend · 清晰锚定的市场分析",
    titleTemplate: "%s · TraFriend",
    description: "面向美国市场的单日杠杆 ETF 情景计算与获利比例分析。",
  },
  common: {
    english: "English",
    chinese: "中文",
    language: "语言",
    mockData: "模拟数据",
    provider: "数据提供方",
    tradingDate: "交易日期",
  },
  header: {
    dashboardAria: "TraFriend 数据面板",
    primaryNavigationAria: "主导航",
    dashboard: "数据面板",
    leverage: "杠杆计算",
    profitRatio: "获利比例",
  },
  footer: {
    product: "TraFriend · 美国市场研究工具",
    disclosure: "仅使用模拟数据 · 不构成投资建议",
  },
  apiStatus: {
    offline: "API 离线",
    connected: "模拟 API 已连接",
  },
  dashboard: {
    phase: "第一阶段工作区",
    eyebrow: "市场分析面板",
    headline: "理解价格关系，",
    headlineMuted: "而不只是查看报价。",
    intro:
      "在 TraFriend 完善数据与计算基础期间，您可以使用确定性的模拟数据探索情景。目前尚未连接实时数据提供方。",
    mode: "模式",
    modeValue: "模拟",
    storage: "存储",
    storageValue: "内存",
    availableNow: "当前可用",
    toolkit: "分析工具箱",
    toolsOnline: "2 / 2 项工具在线",
    openTool: "打开{title}",
    tools: {
      leverage: {
        eyebrow: "情景工具",
        title: "杠杆 ETF 价格计算器",
        description: "在标的资产与其正向或反向杠杆 ETF 之间换算单日目标价格。",
      },
      profitRatio: {
        eyebrow: "持仓成本信号",
        title: "获利比例",
        description: "结合每日收盘价，查看基于模拟持仓成本估算的获利比例。",
      },
    },
    dataPolicyAria: "数据政策",
    referenceTitle: "一组参考价，一个交易日。",
    referenceDescription: "计算情景如何保持统一锚点",
    referenceSteps: [
      {
        title: "采集",
        description: "在设定的隔夜交易时段开始时，记录一组时间一致的配对价格。",
      },
      {
        title: "锁定",
        description: "这组不可变价格将成为当天的每日参考价格版本。",
      },
      {
        title: "计算",
        description: "当天的所有情景计算都使用页面展示的同一组价格锚点。",
      },
    ],
    foundationTitle: "基础能力状态",
    foundationDescription: "第一阶段边界",
    foundations: {
      mockProvider: "确定性模拟数据提供方",
      noCredentials: "浏览器端不保存任何凭证",
      decimalCore: "经过 Decimal 测试的计算核心",
    },
  },
  leveragePage: {
    metadataTitle: "杠杆 ETF 价格计算器",
    metadataDescription: "使用模拟参考价格探索杠杆 ETF 的单日目标价格关系。",
    eyebrow: "工具 / 杠杆计算",
    badge: "由模拟 API 提供",
    title: "杠杆 ETF 价格计算器",
    description: "根据标的资产目标价计算理论 ETF 价格，也可由 ETF 目标价反推标的价格。",
    warning: "仅表示单日理论关系，不是多日价格预测。",
  },
  calculator: {
    genericError: "模拟 API 无法完成此次请求。",
    errors: {
      notFound: "未找到请求的市场数据资源。",
      referenceChanged: "每日参考价格已更新，请重试。",
      referenceUnavailable: "当前无法获取每日参考价格。",
      outOfDomain: "该目标价格超出了单日模型的有效范围。",
      validation: "请输入有效的正数目标价格。",
    },
    toolTitle: "计算杠杆目标价",
    toolDescription: "使用当前选择的模拟产品关系和每日参考价格计算并显示单日理论目标价。",
    invalidToolObject: "需要包含 inputSide 和 targetPrice 的对象。",
    invalidToolInput: "inputSide 或 targetPrice 无效。",
    relationship: "产品关系",
    selectProduct: "选择一个杠杆产品",
    mockReference: "模拟参考价",
    pairLabel: "标的资产与 ETF 配对",
    pairPlaceholder: "选择配对",
    underlyingReference: "标的资产参考价",
    etfReference: "{leverage} ETF 参考价",
    tradingDate: "交易日期 {date}",
    provider: "数据提供方 {provider}",
    calculateFrom: "计算方向",
    targetTab: "{symbol} 目标价",
    targetPrice: "{symbol} 目标价格",
    referenceHelp: "API 将根据参考价格版本 {version} 计算；浏览器不会提供杠杆倍数。",
    calculating: "正在计算…",
    calculate: "计算理论价格",
    output: "计算结果",
    resultTitle: "单日理论计算结果",
    estimatedTarget: "理论目标价",
    dailyLeverage: "每日 {leverage}",
    underlyingMove: "标的资产涨跌幅",
    leveragedMove: "杠杆产品涨跌幅",
    singleDayWarning: "本结果使用单日线性杠杆关系，不属于多日价格预测。",
    readyTitle: "请输入目标价格",
    readyDescription: "选择计算方向并输入目标价，TraFriend 将通过模拟 API 计算单日理论价格关系。",
  },
  profitRatioPage: {
    metadataTitle: "获利比例",
    metadataDescription: "结合股票收盘价查看模拟获利比例的历史数据。",
    eyebrow: "工具 / 获利比例",
    badge: "模拟计算方法",
    title: "获利比例",
    description: "观察处于盈利状态的估算持仓成本占比，并比较它与股价的变化方向。",
    instrument: "标的",
  },
  profitRatio: {
    genericError: "模拟 API 无法加载获利比例数据。",
    unavailableTitle: "获利比例数据不可用",
    emptySeries: "模拟时间序列为空。",
    profitRatio: "获利比例",
    closingPrice: "收盘价",
    chartAria: "七日模拟获利比例与 NVDA 收盘价对比图",
    chartBadge: "1日 · 模拟",
    currentEstimate: "当前估算值",
    final: "最终值",
    sampleChange: "本组样本变化 {value} 个百分点",
    observed: "观测日期 {date}",
    methodology: "{provider} · 计算方法 v{version}",
    historicalComparison: "历史对比",
    ratioVsPrice: "获利比例与收盘价",
    accessibleView: "无障碍数据视图",
    mockObservations: "模拟观测数据",
    date: "日期",
    nvdaClose: "NVDA 收盘价",
    quality: "数据质量",
    methodologyName: "模拟盈利持仓成本比例",
    disclosure:
      "{methodology}。获利比例取决于具体计算方法；第一阶段使用确定性模拟数据，不适合作为投资决策依据。",
  },
};

export const dictionaries: Record<Locale, Dictionary> = {
  en,
  "zh-CN": zhCN,
};

export function interpolate(
  message: string,
  values: Record<string, string | number>,
): string {
  return message.replace(/\{(\w+)\}/g, (placeholder, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key)
      ? String(values[key])
      : placeholder,
  );
}
