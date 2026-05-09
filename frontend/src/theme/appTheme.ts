import type { ThemeConfig } from 'antd'
import antdTheme from 'antd/es/theme'

/**
 * 全局暗色主题（尽量贴近“智造云中台”黑色风格 + 保持 Cursor App 的简洁感）
 *
 * 说明：
 * - AntD 的 darkAlgorithm 负责组件级暗色适配
 * - 我们补充少量 token，让背景/文字对比更柔和（避免纯黑纯白刺眼）
 */
export const appTheme: ThemeConfig = {
  // NOTE: do NOT import `{ theme }` from 'antd' here.
  // The project uses `vite-plugin-imp` to auto-inject styles for `antd` named imports,
  // and it will mistakenly try to resolve `antd/es/theme/style/index.js` (non-existent).
  // Cursor.com 风格：暗色 + 极简（字号保持“原版”观感，不做全局缩小）
  algorithm: antdTheme.darkAlgorithm,
  token: {
    // Cursor 风格：主色用于“Primary Button / Focus”等，不用高饱和亮色
    colorPrimary: '#2f2f33',
    colorPrimaryHover: '#3a3a3f',
    colorPrimaryActive: '#252528',

    // Base（黑白极简：尽量减少“蓝调/彩度”）
    colorBgBase: '#0b0b0c',
    colorBgContainer: '#111113',
    colorBorder: 'rgba(255, 255, 255, 0.10)',

    colorTextBase: '#f4f4f5',
    colorTextSecondary: 'rgba(244, 244, 245, 0.70)',

    // 语义色（更中性、更不刺眼）
    colorSuccess: '#8fb5a3',
    colorWarning: '#d6c08a',
    colorError: '#c07a7a',
    colorInfo: '#8da6c2',

    // Cursor 按钮常用 6px 圆角（你贴的 CSS：border-radius: 6px）
    borderRadius: 6,
    // Cursor 常用高度：24/28（我们对齐 Antd 的 SM=24, default=28, LG=32）
    controlHeight: 28,
    controlHeightSM: 24,
    controlHeightLG: 32,
  },
  components: {
    Button: {
      // 极简：去掉阴影，靠线框与轻微 hover 区分状态
      defaultShadow: 'none',
      primaryShadow: 'none',
      dangerShadow: 'none',

      defaultBg: 'transparent',
      // 对齐你贴的 dashboard-outline-button：outline-color = border-secondary
      defaultBorderColor: 'rgba(255, 255, 255, 0.14)',
      defaultColor: 'rgba(244, 244, 245, 0.92)',

      // 对齐：hover 背景 = bg-tertiary，border 更亮一点
      defaultHoverBg: 'rgba(255, 255, 255, 0.04)',
      defaultHoverBorderColor: 'rgba(255, 255, 255, 0.22)',
      defaultHoverColor: '#ffffff',

      defaultActiveBg: 'rgba(255, 255, 255, 0.06)',
      defaultActiveBorderColor: 'rgba(255, 255, 255, 0.26)',
      defaultActiveColor: '#ffffff',

      // Primary：深色底 + 浅色字（更像 Cursor dashboard-primary-button）
      primaryColor: 'rgba(244, 244, 245, 0.92)',
    },
    Table: {
      borderColor: 'rgba(255, 255, 255, 0.10)',
      headerBg: '#111113',
      headerColor: 'rgba(244, 244, 245, 0.92)',
      headerSplitColor: 'rgba(255, 255, 255, 0.10)',
      rowHoverBg: 'rgba(255, 255, 255, 0.03)',
      rowSelectedBg: 'rgba(255, 255, 255, 0.06)',
      rowSelectedHoverBg: 'rgba(255, 255, 255, 0.08)',

      // 密度：不动字号，只微调 padding（让表格更“干净”）
      cellPaddingBlock: 10,
      cellPaddingInline: 12,
      cellPaddingBlockMD: 8,
      cellPaddingInlineMD: 10,
      cellPaddingBlockSM: 6,
      cellPaddingInlineSM: 8,
    },
    Card: {
      headerBg: '#111113',
      actionsBg: 'transparent',
      extraColor: 'rgba(244, 244, 245, 0.70)',
    },
    Input: {
      activeShadow: 'none',
      errorActiveShadow: 'none',
      warningActiveShadow: 'none',
      hoverBg: 'rgba(255, 255, 255, 0.02)',
      activeBg: 'rgba(255, 255, 255, 0.02)',
      hoverBorderColor: 'rgba(255, 255, 255, 0.18)',
      activeBorderColor: 'rgba(255, 255, 255, 0.22)',
    },
    Modal: {
      headerBg: '#111113',
      contentBg: '#111113',
      footerBg: '#111113',
      titleColor: 'rgba(244, 244, 245, 0.92)',
    },
    Tabs: {
      // 修复:全局 colorPrimary 是深灰(#2f2f33),Tabs 选中标签字色默认用 colorPrimary,
      // 在深色背景下跟背景同色看不见。这里单独给 Tabs 配亮色字 + 蓝灰下划线,
      // 跟主题保持一致(对齐 --color-theme-text-* 体系)。
      itemColor: 'rgba(244, 244, 245, 0.55)',
      itemHoverColor: 'rgba(244, 244, 245, 0.92)',
      itemSelectedColor: 'rgba(244, 244, 245, 0.92)',
      itemActiveColor: 'rgba(244, 244, 245, 0.92)',
      inkBarColor: '#8da6c2',
      titleFontSize: 14,
    },
  },
}

