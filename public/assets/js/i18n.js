export const LOCALES = { zh: 'zh-TW', en: 'en-US', ja: 'ja-JP' };
export const CITY_ORDER = ['Taipei', 'New Taipei', 'Taoyuan', 'Hsinchu', 'Taichung', 'Chiayi', 'Tainan', 'Kaohsiung', 'Yilan', 'Hualien', 'Taitung', 'Nantou', 'Other'];
export const DISTRICT_ORDER = ['Beitou', 'Shilin', 'Neihu', 'Nangang', 'Zhongshan', 'Songshan', 'Xinyi', 'Daan', 'Zhongzheng', 'Wanhua'];

export const COMMON_TRANSLATIONS = {
  zh: { month: '資料月份', loadMonth: '載入月份明細', summaryMode: '快速摘要模式', detailMode: '月份明細模式', detailHint: '房型、來源與提前天數篩選會在載入月份明細後啟用。' },
  en: { month: 'Data month', loadMonth: 'Load monthly details', summaryMode: 'Quick summary mode', detailMode: 'Monthly detail mode', detailHint: 'Room size, source, and lead-time filters become available after monthly details load.' },
  ja: { month: 'データ月', loadMonth: '月別明細を読み込む', summaryMode: 'クイック集計モード', detailMode: '月別明細モード', detailHint: '客室面積、料金ソース、リードタイムの絞り込みは月別明細の読み込み後に利用できます。' },
};

export function mergeTranslations(pageTranslations) {
  for (const language of Object.keys(COMMON_TRANSLATIONS)) {
    Object.assign(pageTranslations[language], COMMON_TRANSLATIONS[language]);
  }
  return pageTranslations;
}
