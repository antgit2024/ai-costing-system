declare module 'tiny-pinyin' {
  const Pinyin: {
    isSupported?: () => boolean
    convertToPinyin: (input: string, separator?: string, keepNonChinese?: string) => string
  }
  export default Pinyin
}


