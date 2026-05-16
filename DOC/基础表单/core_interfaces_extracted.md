## erp-goods.goods.sku.search（条件查询货品）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-06-10 14:28:09.0

说明：首次同步，传参lastMaxId(前一次返回的最大skuId ，第一次传0，后面取前一次查询返回的 最后一条数据的skuId)，不用翻页（内部逻辑会取大于lastMaxId的数据）
首次同步完成后，后面请使用修改时间增量查询
skufield字段和 goodsfield字段可查询1-30 中间省略

常见问题：

请求字段数：27；返回字段数：33

### 请求字段

- cols | String | 必填=True | 固定传参：查询指定列 （示例：goodsId,skuId） | 示例=

- pageIndex | Integer | 必填=True | 分页页数默认为0 | 示例=0

- pageSize | Integer | 必填=True | 分页条数 默认为50 | 示例=50

- isIncludeBlockup | Integer | 必填=False | 是否包含停用数据 （1=包含，其它=不包含） | 示例=0

- goodsNames | String | 必填=False | 货品名称 in | 示例=

- goodsNos | String | 必填=False | 货品编号 in | 示例=

- skuNames | String | 必填=False | 规格名称 in | 示例=

- skuBarcodes | String | 必填=False | 条码 in | 示例=

- ownerType | Integer | 必填=False | 货主类型 (0=货主类型是自己，1=客户) | 示例=

- isPackageGood | Integer | 必填=False | 是否组合装 | 示例=

- skuNos | String | 必填=False | 规格编号 in | 示例=

- skuField1 | String | 必填=False | 规格自定义字段1 in | 示例=

- skuField2 | String | 必填=False | 规格自定义字段2 in | 示例=

- skuField29 | String | 必填=False | 规格自定义字段29 in | 示例=

- skuField30 | String | 必填=False | 规格自定义字段30 in | 示例=

- goodsField1 | String | 必填=False | 货品自定义字段1 in | 示例=

- goodsField2 | String | 必填=False | 货品自定义字段2 in | 示例=

- goodsField29 | String | 必填=False | 货品自定义字段29 in | 示例=

- goodsField30 | String | 必填=False | 货品自定义字段30 in | 示例=

- startDate | String | 必填=False | 创建起始时间 | 示例=2021-08-14 00:00:00

- endDate | String | 必填=False | 创建结束时间 | 示例=2021-09-14 23:59:59

- startDateModifiedSku | String | 必填=False | 起始时间(规格修改时间) | 示例=2021-09-14 23:59:59

- endDateModifiedSku | String | 必填=False | 终止时间(规格修改时间) | 示例=2021-09-14 23:59:59

- startDateModifiedGoods | String | 必填=False | 起始时间(货品修改时间) | 示例=2021-09-14 23:59:59

- endDateModifiedGoods | String | 必填=False | 终止时间(货品修改时间) | 示例=	 2021-09-14 23:59:59

- skuCodes | String | 必填=False | 外部编码  | 示例=123456

- lastMaxId | Long | 必填=True | 上次查询的最大skuId （首次同步必传） | 示例=2216051345374512128

### 返回字段

- goodsId | Long | 货品Id | 示例=1

- goodsName | String | 货品名字 | 示例=

- goodsNo | String | 货品编号 | 示例=

- skuName | String | 规格名称 | 示例=

- skuId | Long | 规格id | 示例=1

- skuBarcode | String | 规格条码 | 示例=

- isBlockup | Integer | 是否停用 | 示例=

- skuNo | String | 规格编号 | 示例=

- imgUrl | String | 规格图片 | 示例=

- goodsMainImgurl | String | 优先取规格图片，没有则取货品主图 | 示例=

- goodsNameEn | String | 英文名称 | 示例=

- cateCode | String | 分类编码 | 示例=

- goodsAlias | String | 别名 | 示例=

- cateFullName | String | 分类全称 | 示例=

- gmtModified | String | 规格修改时间 | 示例=

- goodsGmtModified | String | 货品修改时间 | 示例=

- defaultVendId | Long | 默认供应商id | 示例=1

- retailPrice | Long | 固定成本价 | 示例=1

- isPackageGood | Integer | 是否组合装 | 示例=

- cateId | Integer | 分类id | 示例=1

- cateName | String | 分类名字 | 示例=

- brandId | Integer | 品牌id | 示例=1

- brandName | String | 品牌名字 | 示例=

- goodsMemo | String | 货品备注 | 示例=

- goodsFlag | String | 货品标记 | 示例=

- skuField1 | String | 规格自定义字段1 | 示例=

- skuField2 | String | 规格自定义字段2 | 示例=

- skuField29 | String | 规格自定义字段29 | 示例=

- skuField30 | String | 规格自定义字段30 | 示例=

- goodsField1 | String | 货品自定义字段1 | 示例=

- goodsField2 | String | 货品自定义字段2 | 示例=

- goodsField29 | String | 货品自定义字段29 | 示例=

- goodsField30 | String | 货品自定义字段30 | 示例=

### JSON请求示例

```json

{"ownerType":"","skuField29":"","isPackageGood":"","endDate":"2021-09-14 23:59:59","endDateModifiedSku":"2021-09-14 23:59:59","pageSize":50,"skuField2":"","skuField1":"","goodsField29":"","goodsNos":"","goodsNames":"","endDateModifiedGoods":"\t 2021-09-14 23:59:59","startDateModifiedSku":"2021-09-14 23:59:59","isIncludeBlockup":0,"cols":"","skuBarcodes":"","skuField30":"","goodsField30":"","skuNos":"","skuCodes":"123456","startDateModifiedGoods":"2021-09-14 23:59:59","skuNames":"","pageIndex":0,"goodsField1":"","goodsField2":"","startDate":"2021-08-14 00:00:00"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"skuField29":"","gmtModified":"","goodsNameEn":"","isPackageGood":"","goodsId":"1","skuField2":"","skuField1":"","goodsField29":"","cateName":"","skuName":"","defaultVendId":"1","goodsAlias":"","goodsGmtModified":"","goodsName":"","skuId":"1","skuField30":"","goodsNo":"","goodsField30":"","brandName":"","cateFullName":"","goodsMainImgurl":"","goodsMemo":"","cateCode":"","imgUrl":"","isBlockup":"","cateId":1,"brandId":1,"skuNo":"","goodsField1":"","goodsField2":"","skuBarcode":"","goodsFlag":"","retailPrice":"1"},"contextId":"2086180815808988032"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2086180815808988032"},"subCode":"0130020001"}

```

## erp.storage.goodslist（分页查询货品信息）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2026-02-26 11:55:23.0

说明：首次同步，传参maxSkuId(前一次返回的最大skuId ，第一次传0，后面取前一次查询返回的 最后一条数据的skuId)，不用翻页（内部逻辑会取大于maxSkuId的数据）

常见问题：

请求字段数：23；返回字段数：168

### 请求字段

- pageIndex | Integer | 必填=True | 分页页码 | 示例=0

- pageSize | Integer | 必填=True | 分页页数 | 示例=50

- goodsNo | String | 必填=False | 货品编号 | 示例=A00001

- skuBarcode | String | 必填=False | 条码 | 示例=barcode0001

- goodsName | String | 必填=False | 货品名称 | 示例=NO0001

- skuName | String | 必填=False | 规格名称 | 示例=规格A

- abcCate | String | 必填=False | ABC分类(A类,B类,C类) | 示例=A类

- startDate | String | 必填=False | 货品创建起始时间 | 示例=2021-08-14 00:00:00

- endDate | String | 必填=False | 货品创建结束时间 | 示例=2021-09-14 23:59:59

- startDateModifiedSku | String | 必填=False | 起始时间(规格修改时间) | 示例=2021-09-14 23:59:59

- endDateModifiedSku | String | 必填=False | 终止时间(规格修改时间) | 示例=2021-09-14 23:59:59

- startDateModifiedGoods | String | 必填=False | 起始时间(货品修改时间) | 示例=2021-09-14 23:59:59

- endDateModifiedGoods | String | 必填=False | 终止时间(货品修改时间) | 示例=2021-09-14 23:59:59

- isPackageGood | Integer | 必填=False | 是否组合装（0：否；1：是） | 示例=0

- isBlockup | Integer | 必填=False | 货品是否停用（0：否；1：是） | 示例=0

- skuIsBlockup | Integer | 必填=False | 规格是否停用（0：否；1：是） | 示例=0

- cateName | String | 必填=False | 分类名称 | 示例=奶制品

- assistBarcode | String | 必填=False | 辅助条码（支持批量查询，使用,隔开） | 示例=mb01b,mb01b,zy01,200g/包

- goodsNos | String | 必填=False | 货品编号,多个用,号隔开 | 示例=NO0001,NO002

- isQueryDelete | String | 必填=False | 是否需要返回已删除的货品 传1 需要  不传或者传0 不返回已删除的货品 | 示例=1

- skuBarcodes | String | 必填=False | 条码多个筛选，逗号隔开 | 示例=12134,4213

- skuCodes | String | 必填=False | 外部编码(多个用逗号隔开) | 示例=WB00001

- maxSkuId | Long | 必填=False | 上次查询返回的 最大skuId(就是最后一条 skuId，首次传0) | 示例=124457454645

### 返回字段

- goodsId | Long | 货品ID | 示例=1123123

- goodsNo | String | 货品编号 | 示例=货品编号

- goodsName | String | 货品名称 | 示例=货品名称

- skuName | String | 规格名称 | 示例=规格名称

- skuId | Long | 规格ID | 示例=1212

- skuBarcode | String | 条码 | 示例=code_0001

- unitName | String | 单位 | 示例=个

- cateId | Integer | 分类ID | 示例=12

- cateName | String | 分类 | 示例=服装

- brandId | Integer | 品牌ID | 示例=12

- brandName | String | 品牌 | 示例=活鼎红

- goodsField1 | String | 货品自定义字段1 | 示例=货品自定义字段1

- goodsField2 | String | 货品自定义字段2 | 示例=货品自定义字段2

- goodsField3 | String | 货品自定义字段3 | 示例=货品自定义字段3

- goodsField4 | String | 货品自定义字段4 | 示例=货品自定义字段4

- goodsField5 | String | 货品自定义字段5 | 示例=货品自定义字段5

- goodsField6 | String | 货品自定义字段6 | 示例=货品自定义字段6

- goodsField7 | String | 货品自定义字段7 | 示例=货品自定义字段7

- goodsField8 | String | 货品自定义字段8 | 示例=货品自定义字段8

- goodsField9 | String | 货品自定义字段9 | 示例=货品自定义字段9

- goodsField10 | String | 货品自定义字段10 | 示例=货品自定义字段10

- goodsField11 | String | 货品自定义字段11 | 示例=货品自定义字段11

- goodsField12 | String | 货品自定义字段12 | 示例=货品自定义字段12

- goodsField13 | String | 货品自定义字段13 | 示例=货品自定义字段13

- goodsField14 | String | 货品自定义字段14 | 示例=货品自定义字段14

- goodsField15 | String | 货品自定义字段15 | 示例=货品自定义字段15

- goodsField16 | String | 货品自定义字段16 | 示例=货品自定义字段16

- goodsField17 | String | 货品自定义字段17 | 示例=货品自定义字段17

- goodsField18 | String | 货品自定义字段18 | 示例=货品自定义字段18

- goodsField19 | String | 货品自定义字段19 | 示例=货品自定义字段19

- goodsField20 | String | 货品自定义字段20 | 示例=货品自定义字段20

- goodsField21 | String | 货品自定义字段21 | 示例=货品自定义字段21

- goodsField22 | String | 货品自定义字段22 | 示例=货品自定义字段22

- goodsField23 | String | 货品自定义字段23 | 示例=货品自定义字段23

- goodsField24 | String | 货品自定义字段24 | 示例=货品自定义字段24

- goodsField25 | String | 货品自定义字段25 | 示例=货品自定义字段25

- goodsField26 | String | 货品自定义字段26 | 示例=货品自定义字段26

- goodsField27 | String | 货品自定义字段27 | 示例=货品自定义字段27

- goodsField28 | String | 货品自定义字段28 | 示例=货品自定义字段28

- goodsField29 | String | 货品自定义字段29 | 示例=货品自定义字段29

- goodsField30 | String | 货品自定义字段30 | 示例=货品自定义字段30

- goodsField31 | String | 货品自定义字段31 | 示例=货品自定义字段31

- goodsField32 | String | 货品自定义字段32 | 示例=货品自定义字段32

- goodsField33 | String | 货品自定义字段33 | 示例=货品自定义字段33

- goodsField34 | String | 货品自定义字段34 | 示例=货品自定义字段34

- goodsField35 | String | 货品自定义字段36 | 示例=货品自定义字段36

- goodsField36 | String | 货品自定义字段36 | 示例=货品自定义字段36

- goodsField37 | String | 货品自定义字段37 | 示例=货品自定义字段37

- goodsField38 | String | 货品自定义字段38 | 示例=货品自定义字段38

- goodsField39 | String | 货品自定义字段39 | 示例=货品自定义字段39

- goodsField40 | String | 货品自定义字段40 | 示例=货品自定义字段40

- goodsField41 | String | 货品自定义字段40 | 示例=货品自定义字段40

- goodsField42 | String | 货品自定义字段42 | 示例=货品自定义字段42

- goodsField43 | String | 货品自定义字段43 | 示例=货品自定义字段43

- goodsField44 | String | 货品自定义字段44 | 示例=货品自定义字段44

- goodsField45 | String | 货品自定义字段45 | 示例=货品自定义字段45

- goodsField46 | String | 货品自定义字段46 | 示例=货品自定义字段46

- goodsField47 | String | 货品自定义字段47 | 示例=货品自定义字段47

- goodsField48 | String | 货品自定义字段48 | 示例=货品自定义字段48

- goodsField49 | String | 货品自定义字段49 | 示例=货品自定义字段49

- goodsField50 | String | 货品自定义字段50 | 示例=货品自定义字段50

- skuField1 | String | 规格自定义字段1 | 示例=规格自定义字段1

- skuField2 | String | 规格自定义字段2 | 示例=规格自定义字段2

- skuField3 | String | 规格自定义字段3 | 示例=规格自定义字段3

- skuField4 | String | 规格自定义字段4 | 示例=规格自定义字段4

- skuField5 | String | 规格自定义字段5 | 示例=规格自定义字段5

- skuField6 | String | 规格自定义字段6 | 示例=规格自定义字段6

- skuField7 | String | 规格自定义字段7 | 示例=规格自定义字段7

- skuField8 | String | 规格自定义字段8 | 示例=规格自定义字段8

- skuField9 | String | 规格自定义字段9 | 示例=规格自定义字段9

- skuField10 | String | 规格自定义字段10 | 示例=规格自定义字段10

- skuField11 | String | 规格自定义字段11 | 示例=规格自定义字段11

- skuField12 | String | 规格自定义字段12 | 示例=规格自定义字段12

- skuField13 | String | 规格自定义字段13 | 示例=规格自定义字段13

- skuField14 | String | 规格自定义字段14 | 示例=规格自定义字段14

- skuField15 | String | 规格自定义字段15 | 示例=规格自定义字段15

- skuField16 | String | 规格自定义字段16 | 示例=规格自定义字段16

- skuField17 | String | 规格自定义字段17 | 示例=规格自定义字段17

- skuField18 | String | 规格自定义字段18 | 示例=规格自定义字段18

- skuField19 | String | 规格自定义字段19 | 示例=规格自定义字段19

- skuField20 | String | 规格自定义字段20 | 示例=规格自定义字段20

- skuField21 | String | 规格自定义字段21 | 示例=规格自定义字段21

- skuField22 | String | 规格自定义字段22 | 示例=规格自定义字段22

- skuField23 | String | 规格自定义字段23 | 示例=规格自定义字段23

- skuField24 | String | 规格自定义字段24 | 示例=规格自定义字段24

- skuField25 | String | 规格自定义字段25 | 示例=规格自定义字段25

- skuField26 | String | 规格自定义字段26 | 示例=规格自定义字段26

- skuField27 | String | 规格自定义字段27 | 示例=规格自定义字段27

- skuField28 | String | 规格自定义字段28 | 示例=规格自定义字段28

- skuField29 | String | 规格自定义字段29 | 示例=规格自定义字段29

- skuField30 | String | 规格自定义字段30 | 示例=规格自定义字段30

- skuCode | String | 外部货品编码 | 示例=123

- goodsDesc | String | 货品说明 | 示例=货品说明

- goodsAlias | String | 货品别名 | 示例=货品别名

- goodsField | String | 货品自定义字段，对应吉客云自定义属性 | 示例=货品自定义字段

- skuImgUrl | String | 规格图片 | 示例=http:2qwuqweuq\.png

- extendValue | String | 自定义项 | 示例="{\"extend843337487958029056\":\"121.0000\",\"extend855097154722339968\":\"驱蚊器二去\"}",

- imgUrlList | Array | 货品图片详情 | 示例=

- imgUrlList-goodsId | Long | 货品ID | 示例=121212

- imgUrlList-imgUrl | String | 图片地址 | 示例=http:asasda.png

- imgUrlList-isMainImage | String | 是否主图（0：否；1：是） | 示例=1

- imgUrlList-imagePosition | String | 图片位置main-主图 left-左侧图 right-右侧图 top上侧图 bottom 下侧图  | 示例=left

- imgUrlList-imgKey | String | 图片地址key | 示例=美美哒.png

- skuIsBlockup | Integer | 规格是否停用（0：否；1：是） | 示例=0

- abcCate | String | ABC分类(A类,B类,C类) | 示例=A类

- skuLength | BigDecimal | 长 | 示例=2

- skuWidth | BigDecimal | 宽 | 示例=1

- skuHeight | BigDecimal | 高 | 示例=4

- colorCode | String | 颜色编码 | 示例=1

- colorName | String | 颜色名称 | 示例=4

- sizeCode | String | 尺码编号 | 示例=1

- sizeName | String | 尺寸名称 | 示例=2

- skuWeight | BigDecimal | 重量(g) | 示例=1.2

- volume | BigDecimal | 体积（cm³） | 示例=1

- goodsGmtModified | Date | 货品修改时间 | 示例=1631020179000

- warehouseId | Long | 默认存放仓库ID | 示例=123469988849846

- warehouseName | String | 默认存放仓库名称 | 示例=笛佛仓

- defaultVendId | Long | 默认供应商ID | 示例=129885456456466

- defaultVendName | String | 默认供应商 | 示例=笛佛供应商

- gmtCreate | Date | 货品创建时间 | 示例=1631020179000

- flagData | String | 货品标记 | 示例=货品专用标记,1测试

- skuGmtCreate | Date | 规格级创建时间 | 示例=1631020179000

- skuGmtModified | Date | 规格级修改时间 | 示例=1631020179000

- ownerType | String | 货主类型 | 示例=0

- ownerName | String | 货主名称 | 示例=自己

- mainBarcode | String | 主条码 | 示例=5464aad

- goodsUnit | String | 辅助单位信息 | 示例=list

- goodsUnit-unitName | String | 辅助单位名称 | 示例=个

- goodsUnit-countRate | String | 换算率 | 示例=5.0000000000

- goodsUnit-isBaseUnit | String | 是否为基础单位（0：否；1：是） | 示例=1

- goodsUnit-assistCountRate | String | 辅助单位换算率 | 示例=1

- goodsUnit-goodsId | String | 货品id | 示例=1214414123411

- goodsUnit-baseCountRate | String | 基础单位换算率 | 示例=1

- retailPrice | String | 固定成本价 | 示例=1

- goodsNameEn | String | 货品英文名 | 示例=english

- goodsAttr | Integer | 货品属性（1：成品；2：半成品；3：原料；4：包装材料；5：辅料；6：资产；7：耗材；8：服务；9：设备；10：备件；11：费用） | 示例=1

- cateFullName | String | 分类全称 | 示例=空调

- goodsInfoDescript | Object | 图文描述 | 示例=-

- goodsInfoDescript-sellInfo | String | 货品卖点 | 示例=货品卖点

- goodsInfoDescript-descript | String | 货品描述 | 示例=货品描述

- goodsInfoDescript-goodsVideoUrl | String | 货品视频地址 | 示例=货品视频地址

- goodsInfoDescript-materialImgUrl | String | 透明素材图片地址 | 示例=-

- goodsFileList | Array | 货品附件 | 示例=

- goodsFileList-fileName | String | 文件名称 | 示例=文件名称

- goodsFileList-fileUrl | String | 文件url | 示例=-

- goodsMemo | String | 货品备注 | 示例=这里是货品备注

- memo | String | 规格备注 | 示例=这里是规格备注

- isDelete | String | 是否删除（0：否；1：是） | 示例=0

- isPackageGood | Integer | 是否是组合装 1-是 0-否 | 示例=0

- inStoreProcessing | Boolean | 是否仓内加工  1-是 0-否 | 示例=1

- isCustomizProduction | Boolean | 定制生产（转生产后发货）1-是 0-否 | 示例=1

- isPickupCard | Boolean | 卡券 1-是 0-否 | 示例=1

- isDoorService | Boolean | 需上门安装（发货后转工单) 1-是 0-否 | 示例=1

- isPaidService | Boolean | 虚拟物品/服务(无仓储作业) 1-是 0-否 | 示例=1

- isProductionMaterials | Boolean | 生产物料1-是 0-否 | 示例=1

- isStopSelling | Boolean | 停止销售 1-是 0-否 | 示例=1

- isStopPurchasing | Boolean | 停止采购 1-是 0-否 | 示例=1

- isStockPlan | Boolean | 备货计划 1-是 0-否 | 示例=1

- isGspGoods | Boolean | 是否首营品种 1-是 0-否 | 示例=1

- isCloutManagement | Boolean | 余料管理 1-是 0-否 | 示例=1

- isAssemblyManagement | Boolean | 组装品管理 1-是 0-否 | 示例=1

- isConsignManagement | Boolean | 寄售管理 1-是 0-否 | 示例=1

- isPurchDelivery | Boolean | 即采即发 1-是 0-否 | 示例=1

- isCompensation | Boolean | 是否补差货品 1-是 0-否 | 示例=1

- isDoorInstall | Boolean | 需上门安装 1-是 0-否 | 示例=1

- isSerialManagement | Integer | 是否唯一码管理 （1=开启，其它 =未开启） | 示例=1

- isBatchMgmt | Integer | 是否批次管理（1= 开启，其它 = 未开启） | 示例=1

- skuNo | String | 规格编号 | 示例=规格编号

### JSON请求示例

```json

{"goodsNo":"A00001","skuCodes":"WB00001","endDate":"2021-09-14 23:59:59","isPackageGood":0,"endDateModifiedSku":"2021-09-14 23:59:59","startDateModifiedGoods":"2021-09-14 23:59:59","pageSize":50,"cateName":"奶制品","skuName":"规格A","skuIsBlockup":0,"goodsNos":"NO0001,NO002","isQueryDelete":"1","maxSkuId":"124457454645","endDateModifiedGoods":"2021-09-14 23:59:59","isBlockup":0,"pageIndex":0,"startDateModifiedSku":"2021-09-14 23:59:59","skuBarcode":"barcode0001","abcCate":"A类","assistBarcode":"mb01b,mb01b,zy01,200g/包","goodsName":"NO0001","startDate":"2021-08-14 00:00:00","skuBarcodes":"12134,4213"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"goodsNameEn":"english","isGspGoods":false,"memo":"这里是规格备注","isDoorService":false,"defaultVendId":"129885456456466","skuHeight":4,"isAssemblyManagement":false,"flagData":"货品专用标记,1测试","goodsName":"货品名称","goodsDesc":"货品说明","goodsField8":"货品自定义字段8","goodsField9":"货品自定义字段9","defaultVendName":"笛佛供应商","goodsField10":"货品自定义字段10","goodsField4":"货品自定义字段4","goodsField11":"货品自定义字段11","goodsField5":"货品自定义字段5","goodsField12":"货品自定义字段12","goodsField6":"货品自定义字段6","goodsField13":"货品自定义字段13","goodsField7":"货品自定义字段7","goodsField14":"货品自定义字段14","goodsField15":"货品自定义字段15","goodsField16":"货品自定义字段16","goodsField17":"货品自定义字段17","goodsField18":"货品自定义字段18","goodsField19":"货品自定义字段19","isStopSelling":false,"warehouseId":"123469988849846","brandId":12,"skuNo":"规格编号","goodsField1":"货品自定义字段1","goodsField2":"货品自定义字段2","goodsField3":"货品自定义字段3","skuCode":"123","goodsId":"1123123","warehouseName":"笛佛仓","isCustomizProduction":false,"skuIsBlockup":0,"goodsAlias":"货品别名","sizeName":"2","goodsField":"货品自定义字段","gmtCreate":"1631020179000","goodsAttr":1,"goodsInfoDescript":{"descript":"货品描述","materialImgUrl":"-","sellInfo":"货品卖点","goodsVideoUrl":"货品视频地址"},"isSerialManagement":1,"isDoorInstall":false,"skuBarcode":"code_0001","retailPrice":"1","goodsField40":"货品自定义字段40","skuField29":"规格自定义字段29","ownerType":"0","goodsField41":"货品自定义字段40","imgUrlList":[{"isMainImage":"1","goodsId":"121212","imagePosition":"left","imgKey":"美美哒.png","imgUrl":"http:asasda.png"}],"colorName":"4","isPurchDelivery":false,"goodsField42":"货品自定义字段42","goodsField43":"货品自定义字段43","skuField9":"规格自定义字段9","goodsField44":"货品自定义字段44","skuField8":"规格自定义字段8","skuField25":"规格自定义字段25","isCloutManagement":false,"goodsField45":"货品自定义字段45","skuField7":"规格自定义字段7","skuField26":"规格自定义字段26","isPackageGood":0,"isStockPlan":false,"goodsField46":"货品自定义字段46","skuField6":"规格自定义字段6","skuField27":"规格自定义字段27","goodsField47":"货品自定义字段47","skuField5":"规格自定义字段5","skuField28":"规格自定义字段28","goodsField48":"货品自定义字段48","skuField4":"规格自定义字段4","goodsField49":"货品自定义字段49","skuField3":"规格自定义字段3","skuField2":"规格自定义字段2","skuField1":"规格自定义字段1","extendValue":"\"{\\\"extend843337487958029056\\\":\\\"121.0000\\\",\\\"extend855097154722339968\\\":\\\"驱蚊器二去\\\"}\",","cateName":"服装","isCompensation":false,"skuId":"1212","skuField30":"规格自定义字段30","goodsField50":"货品自定义字段50","skuField18":"规格自定义字段18","skuField19":"规格自定义字段19","skuGmtCreate":"1631020179000","brandName":"活鼎红","unitName":"个","skuField14":"规格自定义字段14","isStopPurchasing":false,"skuField15":"规格自定义字段15","skuField16":"规格自定义字段16","skuField17":"规格自定义字段17","isPickupCard":false,"goodsMemo":"这里是货品备注","skuWidth":1,"skuGmtModified":"1631020179000","volume":1,"cateId":12,"skuField21":"规格自定义字段21","skuField22":"规格自定义字段22","skuField23":"规格自定义字段23","skuField24":"规格自定义字段24","isProductionMaterials":false,"skuField20":"规格自定义字段20","skuWeight":1.2,"goodsField20":"货品自定义字段20","goodsField21":"货品自定义字段21","goodsField22":"货品自定义字段22","goodsField23":"货品自定义字段23","goodsField24":"货品自定义字段24","goodsField25":"货品自定义字段25","goodsField26":"货品自定义字段26","goodsField27":"货品自定义字段27","goodsField28":"货品自定义字段28","goodsField29":"货品自定义字段29","skuName":"规格名称","ownerName":"自己","isConsignManagement":false,"skuField10":"规格自定义字段10","goodsGmtModified":"1631020179000","skuField11":"规格自定义字段11","skuField12":"规格自定义字段12","mainBarcode":"5464aad","goodsUnit":{"countRate":"5.0000000000","isBaseUnit":"1","goodsId":"1214414123411","baseCountRate":"1","assistCountRate":"1","unitName":"个"},"skuField13":"规格自定义字段13","abcCate":"A类","goodsNo":"货品编号","goodsField30":"货品自定义字段30","goodsField31":"货品自定义字段31","goodsField32":"货品自定义字段32","goodsField33":"货品自定义字段33","skuLength":2,"goodsField34":"货品自定义字段34","goodsFileList":[{"fileName":"文件名称","fileUrl":"-"}],"isPaidService":false,"goodsField35":"货品自定义字段36","cateFullName":"空调","isDelete":"0","goodsField36":"货品自定义字段36","goodsField37":"货品自定义字段37","goodsField38":"货品自定义字段38","goodsField39":"货品自定义字段39","inStoreProcessing":false,"isBatchMgmt":1,"colorCode":"1","sizeCode":"1","skuImgUrl":"http:2qwuqweuq\\.png"},"contextId":"2378284552512635520"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2378284552512635520"},"subCode":"0130020001"}

```

## erp-goods.goods.getforqimen（查询吉客云货品档案信息（仿奇门返回））

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-12-26 09:09:20.0

说明：查询吉客云货品档案信息（仿奇门返回）

常见问题：

请求字段数：7；返回字段数：87

### 请求字段

- pageIndex | Integer | 必填=True | 页码（第一页传0） | 示例=1

- pageSize | Integer | 必填=True | 页数 | 示例=50

- goodsCode | String | 必填=False | 货品编号 | 示例=H1234

- barCode | String | 必填=False | 条码 | 示例=SBar1235

- startDate | String | 必填=False | 修改时间开始 | 示例=2020-09-14 13:00:00

- endDate | String | 必填=False | 修改时间结束 | 示例=2020-09-14 14:00:00

- skuFlagNames | String | 必填=False | 标记名称  多个用逗号隔开 | 示例=标记1,标记2

### 返回字段

- data | Array | 货品信息集合 | 示例=

- data-itemCode | Integer | 规格id | 示例=20000102001

- data-itemId | Integer | 值等同于itemCode | 示例=20000102001

- data-goodsCode | String | 货品编号 | 示例=H1234

- data-itemName | String | 货品名称  | 示例=SN123

- data-shortName | String | 货品档案别名 | 示例=JC123

- data-englishName | String | 货品档案英文名 | 示例=JC123

- data-barCode | String | 条码 | 示例=SN123

- data-skuProperty | String | 货品档案的规格名称 | 示例=如红色;XXL

- data-stockUnit | String | 基础单位 | 示例=个

- data-length | Integer | 长（单位：厘米） | 示例=12

- data-width | Integer | 宽（单位：厘米） | 示例=12

- data-height | Integer | 高（单位：厘米） | 示例=12

- data-volume | Integer | 体积（单位：立方厘米） | 示例=12

- data-grossWeight | Integer | 重量（单位g） | 示例=12

- data-color | String | 颜色 | 示例=红色

- data-size | String | 尺码 | 示例=5英尺

- data-categoryId | Integer | 商品类别ID | 示例=11

- data-categoryName | String | 商品类别名称 | 示例=手机

- data-itemType | String | 默认：ZC=正常商品 | 示例=ZC

- data-brandName | String | 品牌名称 | 示例=HM

- data-isShelfLifeMgmt | Integer | 是否质保期管理1=是 0=否 | 示例=1

- data-shelfLife | Integer | 保质期 | 示例=12

- data-shelfLifeUnit | String | 质保期单位Year=年 MONTH=月 | 示例=Year

- data-isBatchMgmt | Integer | 是否批次管理 1=是 0=否 | 示例=1

- data-isPickupCard | Integer | 是否卡券 1=是 0=否 | 示例=1

- data-isPaidService | Integer | 是否虚拟货品 1=是 0=否 | 示例=1

- data-retailPrice | String | 1 | 示例=1

- data-warehouseId | Integer | 仓库ID | 示例=12975748988346646

- data-defaultVendId | Integer | 默认供应商ID | 示例=129888464646465

- data-warehouseName | String | 默认存放仓库名称 | 示例=浙江仓

- data-defaultVendName | String | 默认供应商名称 | 示例=笛佛供应商

- data-ownerType | Integer | 货主类型 0自营，1客户 | 示例=0

- data-ownerId | String | 货主id | 示例=-

- data-ownerName | String | 货主名称 | 示例=-

- data-goodsField1 | String | 货品自定义字段1 | 示例=自定义字段1

- data-goodsField10 | String | 货品自定义字段10 | 示例=自定义字段10

- data-goodsField11 | String | 货品自定义字段11 | 示例=自定义字段11

- data-goodsField12 | String | 货品自定义字段12 | 示例=自定义字段12

- data-goodsField13 | String | 货品自定义字段13 | 示例=自定义字段13

- data-goodsField14 | String | 货品自定义字段14 | 示例=自定义字段14

- data-goodsField15 | String | 货品自定义字段15 | 示例=自定义字段15

- data-goodsField16 | String | 货品自定义字段16 | 示例=自定义字段16

- data-goodsField17 | String | 货品自定义字段17 | 示例=自定义字段17

- data-goodsField18 | String | 货品自定义字段18 | 示例=自定义字段18

- data-goodsField19 | String | 货品自定义字段19 | 示例=自定义字段19

- data-goodsField2 | String | 货品自定义字段2 | 示例=自定义字段2

- data-goodsField6 | String | 货品自定义字段6 | 示例=自定义字段6

- data-goodsField3 | String | 货品自定义字段3 | 示例=自定义字段3

- data-goodsField4 | String | 货品自定义字段4 | 示例=自定义字段4

- data-goodsField5 | String | 货品自定义字段5 | 示例=自定义字段5

- data-goodsField7 | String | 货品自定义字段7 | 示例=自定义字段7

- data-goodsField8 | String | 货品自定义字段8 | 示例=自定义字段8

- data-goodsField9 | String | 货品自定义字段9 | 示例=自定义字段9

- data-goodsField20 | String | 货品自定义字段20 | 示例=自定义字段20

- data-goodsField21 | String | 货品自定义字段21 | 示例=自定义字段21

- data-goodsField22 | String | 货品自定义字段22 | 示例=自定义字段22

- data-goodsField23 | String | 货品自定义字段23 | 示例=自定义字段23

- data-goodsField24 | String | 货品自定义字段24 | 示例=自定义字段24

- data-goodsField25 | String | 货品自定义字段25 | 示例=自定义字段25

- data-goodsField26 | String | 货品自定义字段26 | 示例=自定义字段26

- data-goodsField27 | String | 货品自定义字段27 | 示例=自定义字段27

- data-goodsField28 | String | 货品自定义字段28 | 示例=自定义字段28

- data-goodsField29 | String | 货品自定义字段29 | 示例=自定义字段29

- data-goodsField30 | String | 货品自定义字段30 | 示例=自定义字段30

- data-imgUrl | String | 图片（默认规格图片，没有取货品主图） | 示例={"pic400x400":"https://xxx.jpg","pic0x0":"https://xxx.jpg","pic50x50":"https://xxx.jpg"}

- data-unitInfo | Array | 单位信息 | 示例=-

- data-unitInfo-unitName | String | 单位 | 示例=台

- data-unitInfo-unitId | Integer | 单位ID | 示例=12

- data-unitInfo-countRate | BigDecimal | 转换率 | 示例=1.5

- data-unitInfo-unitWidth | BigDecimal | 宽 | 示例=-

- data-unitInfo-baseWeight | BigDecimal | 基础单位重量 | 示例=1

- data-unitInfo-isBaseUnit | Integer | 是否基础单位 0-否 1-是 | 示例=0

- data-unitInfo-unitHeight | BigDecimal | 高 | 示例=-

- data-unitInfo-unitLength | BigDecimal | 长 | 示例=-

- data-unitInfo-unitVolume | BigDecimal | 体积 | 示例=-

- data-unitInfo-unitWeight | BigDecimal | 单位重量 | 示例=1

- data-unitInfo-baseCountRate | BigDecimal | 基础单位的换算率 | 示例=1

- data-unitInfo-unitVolumeUnit | String | 体积单位 | 示例=-

- data-unitInfo-unitWeightUnit | String | 单位重量单位 | 示例=kg

- data-unitInfo-unitMainBarcode | String | 单位主条码 | 示例=asda

- data-unitInfo-assistCountRate | BigDecimal | 辅助换算率 | 示例=1

- pageInfo | Object | 分页对象 | 示例=1

- pageInfo-pageIndex | Integer |  | 示例=0

- pageInfo-offset | Integer |  | 示例=50

- pageInfo-pageSize | Integer |  | 示例=50

- pageInfo-total | Integer | 总数 | 示例=2000

### JSON请求示例

```json

{"pageIndex":1,"endDate":"2020-09-14 14:00:00","pageSize":50,"goodsCode":"H1234","skuFlagNames":"标记1,标记2","startDate":"2020-09-14 13:00:00","barCode":"SBar1235"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"data":[{"itemCode":"20000102001","itemName":"SN123","defaultVendId":"129888464646465","height":"12","goodsField8":"自定义字段8","goodsField9":"自定义字段9","brandName":"HM","defaultVendName":"笛佛供应商","goodsField10":"自定义字段10","goodsField4":"自定义字段4","goodsField11":"自定义字段11","goodsField5":"自定义字段5","goodsField12":"自定义字段12","goodsField6":"自定义字段6","goodsField13":"自定义字段13","goodsField7":"自定义字段7","goodsField14":"自定义字段14","isPickupCard":1,"goodsField15":"自定义字段15","goodsField16":"自定义字段16","goodsField17":"自定义字段17","goodsField18":"自定义字段18","goodsField19":"自定义字段19","barCode":"SN123","stockUnit":"个","volume":"12","itemId":"20000102001","size":"5英尺","warehouseId":"12975748988346646","goodsField1":"自定义字段1","goodsField2":"自定义字段2","goodsField3":"自定义字段3","shortName":"JC123","englishName":"JC123","itemType":"ZC","goodsField20":"自定义字段20","goodsField21":"自定义字段21","color":"红色","goodsField22":"自定义字段22","goodsField23":"自定义字段23","goodsField24":"自定义字段24","goodsField25":"自定义字段25","goodsField26":"自定义字段26","goodsField27":"自定义字段27","goodsField28":"自定义字段28","goodsField29":"自定义字段29","categoryName":"手机","warehouseName":"浙江仓","skuProperty":"如红色;XXL","isShelfLifeMgmt":1,"unitInfo":[{"unitVolume":"-","unitVolumeUnit":"-","unitHeight":"-","baseCountRate":1,"unitLength":"-","baseWeight":1,"countRate":1.5,"assistCountRate":1,"isBaseUnit":"0","unitName":"台","unitWeight":1,"unitWidth":"-","unitId":12,"unitWeightUnit":"kg","unitMainBarcode":"asda"}],"shelfLife":"12","goodsField30":"自定义字段30","shelfLifeUnit":"Year","isPaidService":1,"length":"12","imgUrl":"{\"pic400x400\":\"https://xxx.jpg\",\"pic0x0\":\"https://xxx.jpg\",\"pic50x50\":\"https://xxx.jpg\"}","grossWeight":"12","isBatchMgmt":1,"width":"12","goodsCode":"H1234","retailPrice":"1","categoryId":11}],"pageInfo":{"pageSize":50,"offset":50,"total":2000,"pageIndex":0}},"contextId":"1914475813357520896"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1914475813357520896"},"subCode":"0130020001"}

```

## erp.goods.customfield（获取货品自定义字段的说明的接口）

接口等级：标准接口; bSubscription：False; bAuthorized：True; postType：2; 最近发布时间：2023-12-04 10:52:59.0

说明：获取自定义字段的说明的接口

常见问题：

请求字段数：0；返回字段数：5

### 请求字段

### 返回字段

- fieldName | String | 自定义字段的英文名字 | 示例=extend835999132354228992

- memo | String | 自定义字段的说明 | 示例=这是自定义字段

- fieldType | String | 自定义字段类型 | 示例=String

- fieldLength | String | 自定义字段的长度 | 示例=255

- fieldCaption | String | 自定义字段的中文名称 | 示例=自定义字段

### JSON请求示例

```json

{}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"memo":"这是自定义字段","fieldName":"extend835999132354228992","fieldType":"String","fieldLength":"255","fieldCaption":"自定义字段"},"contextId":"1832561707101226880"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1832561707101226880"},"subCode":"0130020001"}

```

## erp.goods.skuimportbatch（批量创建货品）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2026-05-11 13:57:41.0

说明：1、批量创建货品 outSkuCode 是2个系统之间的货品匹配关系的唯一依据，如果货品没有outSkuCode则无法用此接口更新货品。请确保规格唯一（用于定位到某一个具体的规格） 吉客云的货品是多规格的模式，根据货品编号+规格名称定位。 相同的货品有多个规格的话，那么货品编号一样，规格名称不一样即可（不同的规格之间的条码也不允许重复） 示例： 货品编号 G0001 货品名称：吉客云冰丝衬衫 规格信息： 规格名称：白色L码 条码：G01B-L 规格名称：白色M码 条码：G01B-M


                                          --------------- 特别说明：同一个货品放在一次里面调用，单次最多支持200。前面请求结束后再请求下一次，减少并发。否则货品可能同步失败或者重复;
2、来源开放平台，不支持货品管理策略;
3、规格名称为空，取‘默认规格’，当‘默认规格’重复时取外部编码（outSkuCode）为规格名称;4、传入的条码如果包含分号，会按照分号拆分识别为多条货品 
5、单次最多传 200个货品

常见问题：

请求字段数：147；返回字段数：4

### 请求字段

- goodsName | String | 必填=True | 货品名字，如果存在则更新(修改可以不传) | 示例=山梅花蜜桃晶采亮肤面膜

- goodsNameEn | String | 必填=False | 货品英文名字 | 示例=qwqwqwq

- goodsNo | String | 必填=True | 货品编号，按照货品编号查询货品(修改可以不传)，新增时如果编号没传，但分类编号/分类名称传了，会按照系统预设规则自动生成编号 | 示例=1196

- goodsAlias | String | 必填=False | 货品别名 | 示例=1231321231

- cateCode | String | 必填=False | 货品的分类编号 | 示例=0101

- cateName | String | 必填=False | 货品的分类名字 | 示例=笔记本

- brandName | String | 必填=False | 品牌名称 | 示例=

- goodsMemo | String | 必填=False | 货品备注 | 示例=

- shelfLife | BigDecimal | 必填=False | 质保期，如果是有效期管理，此项必输 | 示例=3

- shelfLiftUnit | String | 必填=False | 质保期的单位(年、月、天)，如果是有效期管理，此项必输 | 示例=年

- costValuationMethod | Integer | 必填=False | 创建时写入，不支持更新；计价方式0=移动加权平均1=先进先出2=个别计价3=月末一次加权平均法4=固定成本价5=批内移动平均 | 示例=0

- isBatchManagement | Integer | 必填=False | 是否批次管理(1=是，0= 否) | 示例=0

- isSerialManagement | Integer | 必填=False | 是否序列号管理(1=是，0= 否) | 示例=0

- isPeriodManage | Integer | 必填=False | 有效期管理(1=是，0= 否) | 示例=0

- goodsAttr | Integer | 必填=False | 货品属性:1=成品,2=半成品,3=原料,4=包装材料,5=辅料,6=资产,7=耗材,8=服务 | 示例=1

- isProsaleProduct | Integer | 必填=False | 预售品（转预售单）1-是0-否 | 示例=0

- isProxySale | Integer | 必填=False | 代销（转供应商发货）1-是0-否 | 示例=0

- isCustomizProduction | Integer | 必填=False | 定制生产（转生产后发货）1-是0-否 | 示例=0

- isDoorService | Integer | 必填=False | 需上门安装（发货后转工单)1-是0-否 | 示例=0

- isPaidService | Integer | 必填=False | 有偿服务（无库存管理）1-是0-否 | 示例=0

- isPickupCard | Integer | 必填=False | 提货卡券（提货结算冲抵）1-是0-否 | 示例=0

- isProductionMaterials | Integer | 必填=False | 生产物料1-是 0-否 | 示例=0

- unitName | String | 必填=True | 计量单位(修改可以不传) | 示例=件

- outSkuCode | String | 必填=True | 外部编码（必传） | 示例=12232

- skuName | String | 必填=False | 规格名称，不输取‘默认规格’，当‘默认规格’重复时取外部编码 | 示例=规格1

- skuBarcode | String | 必填=False | 条码 | 示例=123fee

- skuLength | BigDecimal | 必填=False | 长 | 示例=1

- skuWidth | BigDecimal | 必填=False | 宽 | 示例=1

- skuHeight | BigDecimal | 必填=False | 高 | 示例=1

- ownerCode | String | 必填=False | 货主编码 | 示例=34343

- skuNo | String | 必填=False | 规格编码 | 示例=HP001

- goodsField1 | String | 必填=False | 自定义字段1（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField2 | String | 必填=False | 自定义字段2（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField3 | String | 必填=False | 自定义字段3（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField4 | String | 必填=False | 自定义字段4（按实际设置的自定义字段类型传参） | 示例= 货品属性B

- goodsField5 | String | 必填=False |  自定义字段5（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField6 | String | 必填=False | 自定义字段6（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField7 | String | 必填=False | 自定义字段7（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField8 | String | 必填=False | 自定义字段8（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField9 | String | 必填=False | 自定义字段9（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField10 | String | 必填=False | 自定义字段10（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField11 | String | 必填=False | 自定义字段11（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField12 | String | 必填=False | 自定义字段12（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField13 | String | 必填=False | 自定义字段13（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField14 | String | 必填=False | 自定义字段14（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField15 | String | 必填=False | 自定义字段15（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField16 | String | 必填=False | 自定义字段16（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField17 | String | 必填=False | 自定义字段17（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField18 | String | 必填=False | 自定义字段18（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField19 | String | 必填=False | 自定义字段19（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField20 | String | 必填=False | 自定义字段20（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField21 | String | 必填=False | 自定义字段21（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField22 | String | 必填=False | 自定义字段22（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField23 | String | 必填=False | 自定义字段23（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField24 | String | 必填=False | 自定义字段24（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField25 | String | 必填=False | 自定义字段25（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField26 | String | 必填=False | 自定义字段26（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField27 | String | 必填=False | 自定义字段27（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField28 | String | 必填=False | 自定义字段28（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField29 | String | 必填=False | 自定义字段29（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField30 | String | 必填=False | 自定义字段30（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField31 | String | 必填=False | 自定义字段31（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField32 | String | 必填=False | 自定义字段32（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField33 | String | 必填=False | 自定义字段33（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField34 | String | 必填=False | 自定义字段34（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField35 | String | 必填=False | 自定义字段35（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField36 | String | 必填=False | 自定义字段36（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField37 | String | 必填=False | 自定义字段37（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField38 | String | 必填=False | 自定义字段38（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField39 | String | 必填=False | 自定义字段39（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField40 | String | 必填=False | 自定义字段40（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField41 | String | 必填=False | 自定义字段41（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField42 | String | 必填=False | 自定义字段42（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField43 | String | 必填=False | 自定义字段43（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField44 | String | 必填=False | 自定义字段44（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField45 | String | 必填=False | 自定义字段45（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField46 | String | 必填=False | 自定义字段46（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField47 | String | 必填=False | 自定义字段47（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField48 | String | 必填=False | 自定义字段48（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField49 | String | 必填=False | 自定义字段49（按实际设置的自定义字段类型传参） | 示例=货品属性B

- goodsField50 | String | 必填=False | 自定义字段50（按实际设置的自定义字段类型传参） | 示例=货品属性B

- abcCate | String | 必填=False | ABC分类(A类,B类,C类) | 示例=A类

- mainBarcode | String | 必填=False | 货品主条码 | 示例=CODE0001

- mainGoodsUrl | String | 必填=False | 货品主图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- leftGoodsUrl | String | 必填=False | 左图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- rightGoodsUrl | String | 必填=False | 右图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- topGoodsUrl | String | 必填=False | 上图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- belowGoodsUrl | String | 必填=False | 下图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- sellInfo | String | 必填=False | 卖点 | 示例=商品卖点

- materialImgUrl | String | 必填=False | 素材图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- goodsVideoUrl | String | 必填=False | 商品视频链接 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- skuImageUrl | String | 必填=False | 规格主图 | 示例=http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D

- descript | String | 必填=False | 货品描述 | 示例=<p>这是很好的书!</p>

- isSyncToItem | String | 必填=False | 1-是 0-否 | 示例=0

- platCateId | String | 必填=False | 淘宝类目id | 示例=110201

- moduleContent | Array | 必填=False | 平台详情信息(json字符串) | 示例=[{         "showOder":2,         "title":"是大V都是",         "type":"2",         "content":"&lt;p&gt;是大V都是&lt;/p&gt;"     } ]

- moduleContent-title | String | 必填=False | 平台目录名称 | 示例=标题

- moduleContent-type | Integer | 必填=False | 描述类型(0-文本,1-图片,2-富文本) | 示例=1

- moduleContent-content | String | 必填=False | 描述内容 | 示例=这是描述

- moduleContent-showOder | String | 必填=False | 目录顺序 | 示例=1

- skuField1 | String | 必填=False | 规格自定义字段1 | 示例=A

- skuField2 | String | 必填=False | 规格自定义字段2 | 示例=A

- skuField3 | String | 必填=False | 规格自定义字段3 | 示例=A

- skuField4 | String | 必填=False | 规格自定义字段4 | 示例=A

- skuField5 | String | 必填=False | 规格自定义字段5 | 示例=A

- skuField6 | String | 必填=False | 规格自定义字段6 | 示例=A

- skuField7 | String | 必填=False | 规格自定义字段7 | 示例=A

- skuField8 | String | 必填=False | 规格自定义字段8 | 示例=A

- skuField9 | String | 必填=False | 规格自定义字段9 | 示例=A

- skuField10 | String | 必填=False | 规格自定义字段10 | 示例=A

- skuField11 | String | 必填=False | 规格自定义字段11 | 示例=A

- skuField12 | String | 必填=False | 规格自定义字段12 | 示例=A

- skuField13 | String | 必填=False | 规格自定义字段13 | 示例=A

- skuField14 | String | 必填=False | 规格自定义字段14 | 示例=A

- skuField15 | String | 必填=False | 规格自定义字段15 | 示例=A

- skuField16 | String | 必填=False | 规格自定义字段16 | 示例=A

- skuField17 | String | 必填=False | 规格自定义字段17 | 示例=A

- skuField18 | String | 必填=False | 规格自定义字段17 | 示例=A

- skuField19 | String | 必填=False | 规格自定义字段19 | 示例=A

- skuField20 | String | 必填=False | 规格自定义字段20 | 示例=A

- skuField21 | String | 必填=False | 规格自定义字段21 | 示例=A

- skuField22 | String | 必填=False | 规格自定义字段22 | 示例=A

- skuField23 | String | 必填=False | 规格自定义字段23 | 示例=A

- skuField24 | String | 必填=False | 规格自定义字段24 | 示例=A

- skuField25 | String | 必填=False | 规格自定义字段25 | 示例=A

- skuField26 | String | 必填=False | 规格自定义字段26 | 示例=A

- skuField27 | String | 必填=False | 规格自定义字段27 | 示例=A

- skuField28 | String | 必填=False | 规格自定义字段28 | 示例=A

- skuField29 | String | 必填=False | 规格自定义字段29 | 示例=A

- skuField30 | String | 必填=False | 规格自定义字段30 | 示例=A

- warehouseCode | String | 必填=False | 存放仓库编码 | 示例=C0001

- fixPrice | BigDecimal | 必填=False | 固定成本价 | 示例=1.20

- skuMemo | String | 必填=False | 规格备注 | 示例=规格备注

- defaultVendCode | String | 必填=False | 默认供应商编号 | 示例=abc

- colorCode | String | 必填=False | 颜色编码 | 示例=123

- sizeCode | String | 必填=False | 尺码编码 | 示例=123

- materialCode | String | 必填=False | 成分编码 | 示例=123

- skuWeight | BigDecimal | 必填=False | 重量  （单位“克” ，优先取skuWeightVal） | 示例=88

- skuWeightVal | BigDecimal | 必填=False | 重量 | 示例=88

- skuWeightUnit | String | 必填=False | 重量单位（g,kg,t） | 示例=kg

- volume | BigDecimal | 必填=False | 体积（单位“cm³” ，优先取skuLengthVal） | 示例=66

- skuLengthVal | BigDecimal | 必填=False | 体积 | 示例=66

- skuLengthUnit | String | 必填=False | 体积单位（cm³,dm³,m³） | 示例=m³

- isNotNeedVirtualWarehouse | Integer | 必填=False | 是否自动添加委外仓（为1时不自动添加) | 示例=1

- lockupLifecycleStr | String | 必填=False | 禁售天数 | 示例=1

- adventLifecycleStr | String | 必填=False | 临期预警天数 | 示例=2

- rejectLifecycleStr | String | 必填=False | 禁收天数 | 示例=3

### 返回字段

- outSkuCode | String | 外部货品编号 | 示例=121212

- success | Boolean | 是否成功，该条明细是否成功 | 示例=true

- errorMessage | String | 错误信息 | 示例=234

- subCode | String | 错误编号  （0031310400 代表条码重复） | 示例=0031310400

### JSON请求示例

```json

[{"adventLifecycleStr":"2","skuImageUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","goodsNameEn":"qwqwqwq","isPeriodManage":0,"rightGoodsUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","isDoorService":0,"isProxySale":0,"skuHeight":1,"shelfLiftUnit":"年","goodsName":"山梅花蜜桃晶采亮肤面膜","goodsField8":"货品属性B","goodsField9":"货品属性B","skuLengthUnit":"m³","goodsField10":"货品属性B","goodsField4":" 货品属性B","goodsField11":"货品属性B","goodsField5":"货品属性B","goodsField12":"货品属性B","isNotNeedVirtualWarehouse":1,"goodsField6":"货品属性B","goodsField13":"货品属性B","goodsField7":"货品属性B","goodsField14":"货品属性B","goodsField15":"货品属性B","mainGoodsUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","goodsField16":"货品属性B","goodsField17":"货品属性B","goodsField18":"货品属性B","goodsField19":"货品属性B","cateCode":"0101","moduleContent":[{"type":1,"showOder":"1","title":"标题","content":"这是描述"}],"skuNo":"HP001","goodsField1":"货品属性B","goodsField2":"货品属性B","goodsField3":"货品属性B","descript":"<p>这是很好的书!</p>","belowGoodsUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","ownerCode":"34343","lockupLifecycleStr":"1","isCustomizProduction":0,"isSyncToItem":"0","goodsAlias":"1231321231","shelfLife":3,"platCateId":"110201","materialCode":"123","skuMemo":"规格备注","goodsAttr":1,"isSerialManagement":0,"skuBarcode":"123fee","materialImgUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","sellInfo":"商品卖点","rejectLifecycleStr":"3","topGoodsUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","goodsField40":"货品属性B","skuField29":"A","goodsField41":"货品属性B","goodsField42":"货品属性B","goodsField43":"货品属性B","skuField9":"A","goodsField44":"货品属性B","skuField8":"A","skuField25":"A","goodsField45":"货品属性B","skuField7":"A","skuField26":"A","goodsField46":"货品属性B","skuField6":"A","skuField27":"A","goodsField47":"货品属性B","skuField5":"A","skuField28":"A","goodsField48":"货品属性B","skuField4":"A","goodsField49":"货品属性B","skuField3":"A","skuField2":"A","skuField1":"A","cateName":"笔记本","skuWeightUnit":"kg","outSkuCode":"12232","defaultVendCode":"abc","skuField30":"A","goodsField50":"货品属性B","skuField18":"A","skuField19":"A","brandName":"","unitName":"件","skuField14":"A","skuField15":"A","skuField16":"A","skuField17":"A","isPickupCard":0,"goodsMemo":"","skuWidth":1,"volume":66,"skuField21":"A","leftGoodsUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","skuField22":"A","isProsaleProduct":0,"goodsVideoUrl":"http://wdgjtest.oss-cn-hangzhou.aliyuncs.com/45/341960689798062080.jpg?Expires=4677564907&OSSAccessKeyId=LTAI2P5paDiiYDCJ&Signature=7gKXbqG2QWeG7sUByBk8J9ummno%3D","skuField23":"A","isProductionMaterials":0,"skuField24":"A","fixPrice":1.20,"skuField20":"A","skuWeight":88,"goodsField20":"货品属性B","skuWeightVal":88,"isBatchManagement":0,"goodsField21":"货品属性B","goodsField22":"货品属性B","goodsField23":"货品属性B","goodsField24":"货品属性B","goodsField25":"货品属性B","costValuationMethod":0,"goodsField26":"货品属性B","goodsField27":"货品属性B","goodsField28":"货品属性B","goodsField29":"货品属性B","warehouseCode":"C0001","skuName":"规格1","skuField10":"A","skuField11":"A","mainBarcode":"CODE0001","skuField12":"A","abcCate":"A类","skuField13":"A","skuLengthVal":66,"goodsNo":"1196","goodsField30":"货品属性B","goodsField31":"货品属性B","goodsField32":"货品属性B","skuLength":1,"goodsField33":"货品属性B","isPaidService":0,"goodsField34":"货品属性B","goodsField35":"货品属性B","goodsField36":"货品属性B","goodsField37":"货品属性B","goodsField38":"货品属性B","goodsField39":"货品属性B","colorCode":"123","sizeCode":"123"}]

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":[{"errorMessage":"234","subCode":"0031310400","success":true,"outSkuCode":"121212"}],"contextId":"2378279163217511040"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2378279163217511040"},"subCode":"0130020001"}

```

## erp-goods-online.item.batchupdateitem（批量更新商品档案）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2026-01-23 09:02:27.0

说明：批量更新商品档案。接口预计25年6月16日晚发布

常见问题：1、updateType 1和2的区别
 （1）updateType=1时表示全量信息覆盖，会使用传入的商品信息全量覆盖itemCode定位到的原商品信息。
 （2）updateType=2时表示增量更新，对于itemName、sellingPrice、itemLengthValue、itemLengthUnit等和itemCode同一级别的基础字段，传入值不为空时才会更新，为空时保持原值。对于itemSkuImageList、propInfoList、itemImageInfoList三个列表不为空时才会覆盖原商品信息的对应列表。对于skuList的每个规格元素，通过matchType参数决定skuBarCode/skuNo定位到原规格信息，规格元素的每个字段不为空时才会更新，否则保持原规格信息的字段值。
（3）需注意，若原商品有两个规格，规格名称/规格条形码分别为：”颜色:1;尺码:a“/”规格条形码a“ 和 ”颜色:1;尺码:b“/"规格条形码b", 增量更新时传入skuList中，需包含条形码”规格条形码a“和"规格条形码b"（否则会认为原始规格被删除，新增了一个规格），且规格名称入参是itemSkuImageList销售属性笛卡尔积组合其中之一时（否则该规格元素会被忽略），才能对这两个原规格进行增量更新。具体规格名称组装规范见接口文档skuName参数说明。
2、companyCode和departCode
考虑到公司和部门信息通常不会变化，不管updateType值是什么，始终做增量更新。
3、此接口只会更新未停用、未删除且审核状态非待审核的商品。
4、每次最多支持更新50个itemCode不重复的商品信息。

请求字段数：62；返回字段数：6

### 请求字段

- updateType | Integer | 必填=True | 更新类型 1-全量信息覆盖 2-增量更新，商品级别单个字段不为空才更新，列表不为空才覆盖。 | 示例=2

- inputItemList | Array | 必填=True | 要更新的商品列表 | 示例=要更新的商品列表

- inputItemList-catePathName | String | 必填=False | 商品类目路径 | 示例=笔记本电脑

- inputItemList-itemName | String | 必填=False | 商品标题 | 示例=商品标题

- inputItemList-itemNo | String | 必填=False | 商品货号 | 示例=商品货号

- inputItemList-itemCode | String | 必填=True | 商品编码,定位要更新的商品（忽略大小写），inputItemList数组中每个元素的此字段需唯一 | 示例=商品编码

- inputItemList-itemBarcode | String | 必填=False | 商品条形码 | 示例=商品条形码

- inputItemList-brandName | String | 必填=False | 品牌 | 示例=品牌

- inputItemList-sellPoint | String | 必填=False | 商家卖点 | 示例=商家卖点

- inputItemList-sellingPrice | BigDecimal | 必填=False | 未划线价 | 示例=1000

- inputItemList-originalPrice | BigDecimal | 必填=False | 未划线价 | 示例=100

- inputItemList-costPrice | BigDecimal | 必填=False | 成本价 | 示例=1000

- inputItemList-quantity | BigDecimal | 必填=False | 商品总记库存数量，无规格商品取传入的此字段值， 有规格商品会根据规格库存求和 | 示例=100

- inputItemList-itemLengthValue | BigDecimal | 必填=False | 商品长度，长度和长度单位需同时为空或同时非空 | 示例=12

- inputItemList-itemLengthUnit | String | 必填=False | 商品长度单位(mm,cm,m)，长度和长度单位需同时为空或同时非空 | 示例=mm

- inputItemList-itemWidthValue | BigDecimal | 必填=False | 商品宽度，宽度和宽度单位需同时为空或同时非空 | 示例=12

- inputItemList-itemWidthUnit | String | 必填=False | 商品宽度单位(cm,mm,m), 宽度和宽度单位需同时为空或同时非空 | 示例=mm

- inputItemList-itemHeightValue | BigDecimal | 必填=False | 商品高度(cm,mm,m),高度和高度单位需同时为空或同时非空 | 示例=12

- inputItemList-itemHeightUnit | String | 必填=False | 商品高度单位(cm,mm,m)，高度和高度单位需同时为空或同时非空 | 示例=mm

- inputItemList-newItemWeight | BigDecimal | 必填=False | 商品重量，重量和重量单位需同时为空或同时非空 | 示例=12

- inputItemList-unitOfWeight | String | 必填=False | 重量单位(g,kg)，重量和重量单位需同时为空或同时非空 | 示例=g

- inputItemList-pcDescription | String | 必填=False | 电脑端详情 | 示例=<p>这个是电脑端详情</p>

- inputItemList-wapDescription | String | 必填=False | 手机端详情 | 示例=<p>手机端详情</p>

- inputItemList-companyCode | String | 必填=False | 公司编码 | 示例=公司编码

- inputItemList-departCode | String | 必填=False | 部门编码。部门编码不为空时，公司编码必填 | 示例=部门编码

- inputItemList-itemSkuImageList | Array | 必填=False | itemSkuImageList，skuList和itemSkuImageList需同时为空或同时非空，具体细节见常见问题栏 | 示例=itemSkuImageList

- inputItemList-itemSkuImageList-propName | String | 必填=True | 销售规格属性名称 | 示例=颜色

- inputItemList-itemSkuImageList-isImageProp | Integer | 必填=False | 是否为图片属性 0-否 1-是(一个商品只能有一个图片属性) | 示例=1

- inputItemList-itemSkuImageList-propShowOrder | Integer | 必填=True | 销售属性名称排序 | 示例=1

- inputItemList-itemSkuImageList-skuPropValueList | Array | 必填=True | 销售属性值 | 示例=[                     {                         "propValue":"60GB",                         "showOrder":0,                         "imageJson":[                             {                                 "imageUrl":"https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/erp/364965794411037696/1640642568289028480.jpg?Expires=4832379835&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=c2mxng7bWQrV68u0fDg56eZA0qE%3D",                                 "imageType":"1",                                 "showOrder":0                             }                         ]                     }

- inputItemList-itemSkuImageList-skuPropValueList-propValue | String | 必填=True | 销售属性值 | 示例=红色

- inputItemList-itemSkuImageList-skuPropValueList-showOrder | Integer | 必填=False | 销售属性值排序(注意一定要传,且不要相等,否则会导致上传到平台排序发生变发) | 示例=1

- inputItemList-itemSkuImageList-skuPropValueList-imageJson | String | 必填=False | 销售规格规格(只有当isImageProp=1时,imageJson才生效) | 示例=[                             {                                 "imageUrl":"https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/erp/364965794411037696/1640642568289028480.jpg?Expires=4832379835&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=c2mxng7bWQrV68u0fDg56eZA0qE%3D",                                 "imageType":"1",                                 "showOrder":0                             }                         ]                     }

- inputItemList-itemSkuImageList-skuPropValueList-imageJson-imageUrl | String | 必填=False | 图片地址 | 示例=https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/erp/364965794411037696/1640642568289028480.jpg?Expires=4832379835&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=c2mxng7bWQrV68u0fDg56eZA0qE%3D

- inputItemList-itemSkuImageList-skuPropValueList-imageJson-imageType | Integer | 必填=False | 规格图片类型(1-规格主图 2-规格透明素材图) | 示例=1

- inputItemList-itemSkuImageList-skuPropValueList-imageJson-showOrder | Integer | 必填=False | 规格图片排序 | 示例=1

- inputItemList-skuList | Array | 必填=False | 规格列表，skuList和itemSkuImageList需同时为空或同时非空，具体细节见常见问题栏 | 示例=skuList

- inputItemList-skuList-skuName | String | 必填=True | 规格名称:注意规格名组装规范(规格名称+:+规格值,多个用;分割,规格名称的排序必须跟销售属性列表的规格名称排序一样,否则视为无效规格:例如:规格属性颜色 排序1  skuName的第一个销售属性必须是颜色,规格值也按照销售属性值的排序排列) | 示例=硬盘容量:60GB;颜色分类:黄色

- inputItemList-skuList-skuBarcode | String | 必填=False | 规格条码；规格条码、规格编码必传其一，用于定位原始商品规格（忽略大小写） | 示例=69001921271

- inputItemList-skuList-skuNo | String | 必填=False | 	 规格编码；规格条码、规格编码必传其一，当matchType为1时用于定位原始商品规格（忽略大小写） | 示例=A00002

- inputItemList-skuList-quantity | BigDecimal | 必填=False | 规格库存 | 示例=10000

- inputItemList-skuList-showOrder | Integer | 必填=False | 规格排序 | 示例=1

- inputItemList-skuList-newSkuWeight | BigDecimal | 必填=False | 规格重量，规格重量和规格重量单位需同时为空或同时非空 | 示例=100

- inputItemList-skuList-unitOfWeight | String | 必填=False | 规格重量单位(g,kg) ，规格重量和规格重量单位需同时为空或同时非空 | 示例=g

- inputItemList-skuList-sellingPrice | BigDecimal | 必填=False | 未划线价 | 示例=100

- inputItemList-skuList-originalPrice | BigDecimal | 必填=False | 规格划线价 | 示例=37.5

- inputItemList-skuList-costPrice | BigDecimal | 必填=False | 成本价 | 示例=111

- inputItemList-skuList-skuMainImageUrl | String | 必填=False | 规格主图，优先使用此处传入的，为空默认取itemSkuImageList中的对应一级销售属性第一张规格主图 | 示例=https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/erp/1270206651679120512/1626693631010179456.jpg?Expires=4830716992&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=IM8%2F9A%2FynBBZM6c3UPnG43blIhU%3D

- inputItemList-skuList-offShelfStatus | Integer | 必填=False | 规格上下架状态: 1-下架 0-上架。部分平台规格级别也有上下架状态。为了兼容老商品数据，null也表示上架状态 | 示例=0

- inputItemList-propInfoList | Array | 必填=False | propInfoList | 示例=propInfoList

- inputItemList-propInfoList-propName | String | 必填=False | 产品属性名称 | 示例=品牌

- inputItemList-propInfoList-propIndex | Integer | 必填=True | 产品属性排序 | 示例=2

- inputItemList-propInfoList-propValue | String | 必填=False | 产品属性值(当产品属性名称有时,产品属性值必填)。多个属性值可以英文逗号分割 | 示例=联想

- inputItemList-groupRelInfoList | Array | 必填=False | 商品分组信息 | 示例=[{"groupId":123,"groupPath":"分组1"}]

- inputItemList-groupRelInfoList-groupPath | String | 必填=False | 分组名称(取erp-goods-online.item.getItemGroup接口返回的groupName字段) | 示例=分组1

- inputItemList-groupRelInfoList-groupId | Integer | 必填=True | 商品分组id(取erp-goods-online.item.getItemGroup接口返回的groupId字段) | 示例=123

- inputItemList-itemImageInfoList | Array | 必填=False | itemImageInfoList | 示例=itemImageInfoList

- inputItemList-itemImageInfoList-imageUrl | String | 必填=False | 商品图片地址 | 示例=商品图片

- inputItemList-itemImageInfoList-imageItem | Integer | 必填=False | 商品图片(0-商品主图电脑端 1-商品主图手机端 2-视频封面图 3-其他图片 4-平台资质图 5-视频) | 示例=1

- inputItemList-itemImageInfoList-imageType | Integer | 必填=True | 商品图片类型(0-主图  1-平铺白底图  2-透明素材图 3-商品竖图 4-商品资质图 5-视频封面图 6-质检报告图 7-吊牌图 8-平台资质图 9-视频) | 示例=1

- inputItemList-itemImageInfoList-imageIndex | Integer | 必填=False | 商品图片排序 | 示例=10

- matchType | Integer | 必填=False | 默认是0 匹配类型 0-根据skuBarcode进行匹配规格 1-根据skuNo进行匹配规格 | 示例=0

### 返回字段

- itemCode | String | 入参的商品编码原样返回 | 示例=2025-A1

- itemId | Long | 更新的吉客云商品id，通过itemCode找到的吉客云商品定位信息 | 示例=2124223723690492672

- itemName | String | 入参的商品名称原样返回 | 示例=铺货商品-rn001

- isSuccess | Integer | 是否更新成功 1-成功 0-失败 | 示例=1

- errorMsg | String | isSuccess=0时一定会返回 | 示例=更新失败的原因

- relationId | Long | 关联id 如果设置商品资料/平台副本变更后自动同步到网店 根据此id调用erp-goods-online.item.getItemUploadTaskRelation 去查询上传任务id | 示例=15649461564

### JSON请求示例

```json

{"inputItemList":[{"sellPoint":"商家卖点","itemWidthValue":12,"skuList":[{"offShelfStatus":0,"originalPrice":37.5,"newSkuWeight":100,"skuMainImageUrl":"https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/erp/1270206651679120512/1626693631010179456.jpg?Expires=4830716992&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=IM8%2F9A%2FynBBZM6c3UPnG43blIhU%3D","skuName":"硬盘容量:60GB;颜色分类:黄色","sellingPrice":100,"unitOfWeight":"g","quantity":10000,"costPrice":111,"skuNo":"A00002","showOrder":1,"skuBarcode":"69001921271"}],"originalPrice":100,"itemCode":"商品编码","itemHeightUnit":"mm","itemNo":"商品货号","itemWidthUnit":"mm","itemSkuImageList":[{"propName":"颜色","skuPropValueList":[{"imageJson":{"imageUrl":"https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/erp/364965794411037696/1640642568289028480.jpg?Expires=4832379835&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=c2mxng7bWQrV68u0fDg56eZA0qE%3D","imageType":1,"showOrder":1},"propValue":"红色","showOrder":1}],"isImageProp":1,"propShowOrder":1}],"itemName":"商品标题","sellingPrice":1000,"newItemWeight":12,"unitOfWeight":"g","itemHeightValue":12,"companyCode":"公司编码","brandName":"品牌","quantity":100,"wapDescription":"<p>手机端详情</p>","propInfoList":[{"propName":"品牌","propIndex":2,"propValue":"联想"}],"itemBarcode":"商品条形码","costPrice":1000,"itemLengthUnit":"mm","pcDescription":"<p>这个是电脑端详情</p>","catePathName":"笔记本电脑","departCode":"部门编码","itemLengthValue":12,"itemImageInfoList":[{"imageUrl":"商品图片","imageType":1,"imageItem":1,"imageIndex":10}]}],"updateType":2}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":[{"itemId":"2124223723690492672","itemName":"铺货商品-rn001","itemCode":"2025-A1","isSuccess":1,"errorMsg":"更新失败的原因"}],"contextId":"2243461955021701888"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2243461955021701888"},"subCode":"0130020001"}

```

## erp-goods-online.item.details（获取商品库商品信息）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2024-05-27 16:55:56.0

说明：1、单次最多只能批量获取10个商品信息，超出部分会被忽略。
2、多个商品ID使用英文逗号分隔。
3、此接口不能获取从网店下载的商品信息。

常见问题：1、为什么在商品库可以看到商品，但是没法使用这个接口获取到商品数据？
这个商品有可能是从网店下载的，目前暂不支持获取从网店下载的商品信息。

请求字段数：1；返回字段数：61

### 请求字段

- itemIds | String | 必填=True | 要获取商品信息的商品ID，多个使用英文逗号分隔，最多10个 | 示例=1920452605616621184

### 返回字段

- result | Array | 返回数据 | 示例=

- result-itemId | Long | 商品ID | 示例=12121

- result-cateId | String | 类目ID | 示例=162103

- result-itemNo | String | 商品货号 | 示例=IZ-056-A012

- result-cateName | String | 类目名称 | 示例=女装/女士精品>>毛衣

- result-itemCode | String | 商品条码 | 示例=6956221545

- result-itemName | String | 商品名称 | 示例=测试奶奶春秋针织开衫薄款外套妈妈加绒上衣大码60岁老年人女太太春装

- result-quantity | BigDecimal | 库存数量 | 示例=12456

- result-brandName | String | 品牌名称 | 示例=老奶奶牌

- result-costPrice | BigDecimal | 成本价 | 示例=100

- result-itemWidth | Integer | 商品宽度 | 示例=20

- result-sellPoint | String | 商品卖点 | 示例=奶奶春秋针织开衫薄款

- result-itemHeight | Integer | 商品高度 | 示例=60

- result-itemLength | Integer | 商品长度 | 示例=12

- result-itemBarcode | String | 商品条码 | 示例=695612452

- result-mainImageUrl | String | 商品主图网址 | 示例=http://

- result-sellingPrice | BigDecimal | 售卖价 | 示例=141

- result-unitOfWeight | String | 商品重量单位，kg、g | 示例=kg

- result-newItemWeight | BigDecimal | 商品重量 | 示例=0.5

- result-originalPrice | BigDecimal | 市场价 | 示例=172

- result-transparentImageUrl | String | 透明图网址 | 示例=http://

- result-discount | BigDecimal | 折扣 | 示例=0.8

- result-isManySku | Integer | 规格类型，2多规格 1单规格 0无规格 | 示例=2

- result-itemWidthUnit | String | 商品宽度单位，cm,mm,m | 示例=cm

- result-pcDescription | String | 商品PC详情 | 示例=<p></p>

- result-itemHeightUnit | String | 商品高度单位，cm,mm,m | 示例=cm

- result-itemLengthUnit | String | 商品长度单位，mm,cm,m | 示例=cm

- result-wapDescription | String | 商品移动端详情 | 示例=<p></p>

- result-skuList | Object | 规格列表 | 示例=[]

- result-skuList-skuId | String | 商品库规格ID | 示例=1920452605994108546

- result-skuList-skuNo | String | 规格编号 | 示例=嘉花卡-8032加绒-28

- result-skuList-skuName | String | 规格名称 | 示例=颜色分类:浅驼加绒;尺码:2XL 建议115-130斤

- result-skuList-quantity | BigDecimal | 规格库存 | 示例=700

- result-skuList-costPrice | BigDecimal | 成本价 | 示例=100

- result-skuList-showOrder | Integer | 规格排序值 | 示例=10

- result-skuList-skuBarcode | String | 规格条码 | 示例=6933333

- result-skuList-skuNameJson | String | 规格维度的属性值列表 | 示例=[{\"propValue\":\"浅驼加绒\",\"propName\":\"颜色分类\"},{\"propValue\":\"2XL 建议115-130斤\",\"propName\":\"尺码\"}]

- result-skuList-newSkuWeight | BigDecimal | 规格重量 | 示例=500

- result-skuList-sellingPrice | BigDecimal | 售卖价 | 示例=170

- result-skuList-unitOfWeight | String | 规格重量单位，g，kg | 示例=g

- result-skuList-originalPrice | BigDecimal | 市场价 | 示例=172

- result-skuList-skuMainImageUrl | String | 规格图片网址 | 示例=https://

- result-propInfoList | Array | 商品属性列表 | 示例=[]

- result-propInfoList-propId | Integer | 属性值ID | 示例=156798

- result-propInfoList-propName | String | 属性名称 | 示例=成分含量

- result-propInfoList-propIndex | Integer | 属性顺序 | 示例=1

- result-propInfoList-propValue | String | 属性值 | 示例=91%（含）—95%（含）%

- result-itemSkuImageList | Array | 规格图列表 | 示例=[]

- result-itemSkuImageList-propName | String | 规格属性名称 | 示例=颜色分类

- result-itemSkuImageList-imageJson | String | 规格图片列表 | 示例=[{\"imageUrl\":\"https://1.jpeg\",\"showOrder\":0,\"imageType\":\"1\"},{\"imageUrl\":\"https://2.jpeg\",\"showOrder\":1,\"imageType\":\"1\"},{\"imageUrl\":\"3.jpeg\",\"showOrder\":2,\"imageType\":\"1\"}]

- result-itemSkuImageList-propValue | String | 规格属性值 | 示例=浅驼单款

- result-remark | String | 商品备注 | 示例=balabala

- result-departId | String | 部门ID | 示例=1737870295244506624

- result-companyId | String | 公司ID | 示例=1690630244639213056

- result-departName | String | 部门名称 | 示例=a

- result-companyName | String | 公司名称 | 示例=老奶奶公司

- result-itemImageInfoList | Array | 商品图片列表 | 示例=[]

- result-itemImageInfoList-imageUrl | String | 图片网址 | 示例=http://

- result-itemImageInfoList-imageItem | Integer | 图片类型，0商品图电脑端 1商品图手机端 2 3:4竖图 3其他图片 4平台资质图 5视频 | 示例=0

- result-itemImageInfoList-imageType | Integer | 图片类型 0主图 1白底图 2透明图 3竖图 4资质图 5 3:4竖图 6质检报告 7吊牌图 8平台资质图 9视频 | 示例=0

- result-itemImageInfoList-imageIndex | Integer | 图片顺序 | 示例=0

### JSON请求示例

```json

{"itemIds":"1920452605616621184"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":[{"result":[{"sellPoint":"奶奶春秋针织开衫薄款","skuList":{"originalPrice":172,"newSkuWeight":500,"skuMainImageUrl":"https://","skuName":"颜色分类:浅驼加绒;尺码:2XL 建议115-130斤","skuNameJson":"[{\\\"propValue\\\":\\\"浅驼加绒\\\",\\\"propName\\\":\\\"颜色分类\\\"},{\\\"propValue\\\":\\\"2XL 建议115-130斤\\\",\\\"propName\\\":\\\"尺码\\\"}]","sellingPrice":170,"unitOfWeight":"g","skuId":"1920452605994108546","quantity":700,"costPrice":100,"skuNo":"嘉花卡-8032加绒-28","showOrder":10,"skuBarcode":"6933333"},"originalPrice":172,"itemCode":"6956221545","itemHeight":60,"companyName":"老奶奶公司","discount":0.8,"itemHeightUnit":"cm","remark":"balabala","itemNo":"IZ-056-A012","itemWidthUnit":"cm","cateName":"女装/女士精品>>毛衣","itemSkuImageList":[{"imageJson":"[{\\\"imageUrl\\\":\\\"https://1.jpeg\\\",\\\"showOrder\\\":0,\\\"imageType\\\":\\\"1\\\"},{\\\"imageUrl\\\":\\\"https://2.jpeg\\\",\\\"showOrder\\\":1,\\\"imageType\\\":\\\"1\\\"},{\\\"imageUrl\\\":\\\"3.jpeg\\\",\\\"showOrder\\\":2,\\\"imageType\\\":\\\"1\\\"}]","propName":"颜色分类","propValue":"浅驼单款"}],"itemName":"测试奶奶春秋针织开衫薄款外套妈妈加绒上衣大码60岁老年人女太太春装","sellingPrice":141,"newItemWeight":0.5,"unitOfWeight":"kg","itemWidth":20,"departId":"1737870295244506624","mainImageUrl":"http://","departName":"a","brandName":"老奶奶牌","quantity":12456,"wapDescription":"<p></p>","propInfoList":[{"propId":156798,"propName":"成分含量","propIndex":1,"propValue":"91%（含）—95%（含）%"}],"itemBarcode":"695612452","costPrice":100,"itemLength":12,"itemLengthUnit":"cm","pcDescription":"<p></p>","isManySku":2,"itemId":"12121","companyId":"1690630244639213056","cateId":"162103","transparentImageUrl":"http://","itemImageInfoList":[{"imageUrl":"http://","imageType":0,"imageItem":0,"imageIndex":0}]}]}],"contextId":"1959580087118823808"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1959580087118823808"},"subCode":"0130020001"}

```

## erp.goods.assistbarcodecreate（添加辅助条码）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2024-06-27 16:08:00.0

说明：添加辅助条码

常见问题：

请求字段数：9；返回字段数：0

### 请求字段

- goodsId | Long | 必填=False | 货品Id | 示例=125863695236654

- goodsName | String | 必填=False | 货品名称 | 示例=面膜

- goodsNo | String | 必填=False | 货品编号 | 示例=MM001

- skuId | Long | 必填=False | 规格Id，（必须传skuId，skuBarcode，outskuCode其中一项） | 示例=152369584425233

- skuName | String | 必填=False | 规格名 | 示例=中

- unitName | String | 必填=True | 单位 | 示例=袋

- assistBarcode | String | 必填=True | 辅助条码 | 示例=MM_001

- outSkuCode | String | 必填=False | 外部编码，（必须传skuId，skuBarcode，outskuCode其中一项） | 示例=e123

- skuBarcode | String | 必填=False | 货品主条码，（必须传skuId，skuBarcode，outskuCode其中一项） | 示例=a123

### 返回字段

### JSON请求示例

```json

{"goodsNo":"MM001","skuName":"中","unitName":"袋","goodsId":"125863695236654","skuBarcode":"a123","assistBarcode":"MM_001","goodsName":"面膜","skuId":"152369584425233","outSkuCode":"e123"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{},"contextId":"1982024063913495040"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1982024063913495040"},"subCode":"0130020001"}

```

## erp.goods.assistbarcodeupdate（批量更新辅助条码）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-03-27 14:42:26.0

说明：批量更新辅助条码

常见问题：

请求字段数：3；返回字段数：5

### 请求字段

- skuId | Long | 必填=True | 规格id | 示例=5452234

- oldAssistBarcode | String | 必填=False | 原辅助条码 | 示例=3131

- newAssistBarcode | String | 必填=False | 新辅助条码 | 示例=32131

### 返回字段

- skuId | Long | 规格id(关联规格信息) | 示例=619477311930008320

- oldAssistBarcode | String | 原辅助条码 | 示例=A_0001

- newAssistBarcode | String | 新辅助条码 | 示例=121231

- isSuccess | Integer | 是否有误(是否更新成功0失败) | 示例=0

- msg | String | 错误信息(错误信息) | 示例=条码存在

### JSON请求示例

```json

[{"oldAssistBarcode":"3131","skuId":"5452234","newAssistBarcode":"32131"}]

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"msg":"条码存在","oldAssistBarcode":"A_0001","skuId":"619477311930008320","newAssistBarcode":"121231","isSuccess":0},"contextId":"2179844724344849922"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2179844724344849922"},"subCode":"0130020001"}

```

## erp.storage.assistbarcode（辅助条码查询）

接口等级：免费接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2023-05-30 08:35:32.0

说明：辅助条码查询

常见问题：

请求字段数：1；返回字段数：1

### 请求字段

- skuId | String | 必填=False | 规格id（支持批量查询，使用,隔开） | 示例=1

### 返回字段

- data | Array | 辅助条码 | 示例=[FZ001,FZ002]

### JSON请求示例

```json

{"skuId":"1"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"data":"[FZ001,FZ002]"},"contextId":null},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":null},"subCode":"0130020001"}

```

## erp-goods.pricelist.get（货品价目查询）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2026-05-08 11:45:28.0

说明：开放平台货品价目查询

常见问题：

请求字段数：18；返回字段数：19

### 请求字段

- pageSize | Integer | 必填=False | 每页页数 | 示例=50

- pageIndex | Integer | 必填=False | 页码 | 示例=0

- cols | String | 必填=True | 查询指定列(多个中间逗号隔开) | 示例=skuId,price1

- skuIds | String | 必填=False | 规格ids(多个中间逗号隔开) | 示例=111,222,333

- skuBarcodes | String | 必填=False | 条码(多个中间逗号隔开) | 示例=1,2,3

- skuNames | String | 必填=False | 规格(多个中间逗号隔开) | 示例=1,2,3

- goodsIds | String | 必填=False | 货品ids(多个中间逗号隔开) | 示例=1,2,3

- goodsNos | String | 必填=False | 货品编号(多个中间逗号隔开) | 示例=1,2,3

- goodsNames | String | 必填=False | 货品名称(多个中间逗号隔开) | 示例=1,2,3

- unitNames | String | 必填=False | 单位(多个中间逗号隔开) | 示例=1,2,3

- currencyCodes | String | 必填=False | 币种(多个中间逗号隔开) | 示例=1,2,3

- isDeletes | String | 必填=False | 是否删除(多个中间逗号隔开,0 = 未删除，1= 删除 ，不传默认查未删除的) | 示例=0,1

- isCurrentActive | Integer | 必填=False | 是否生效(0 = 未生效，1= 生效 ) | 示例=1

- groupId | Long | 必填=False | 销售范围id | 示例=4499145120495627521

- gmtCreateStart | String | 必填=False | 创建时间 起始  >= | 示例=2026-01-01

- gmtCreateEnd | String | 必填=False | 创建时间 结束  < | 示例=2026-02-01

- gmtModifiedStart | String | 必填=False | 修改时间 起始 >= | 示例=2026-01-01

- gmtModifiedEnd | String | 必填=False | 修改时间 结束 < | 示例=2026-02-01

### 返回字段

- skuId | Long | 规格id | 示例=4499145120495627521

- skuName | String | 规格名称 | 示例=规格名

- skuBarcode | String | 条形码 | 示例=条码111

- goodsId | Long | 货品id | 示例=4499145120495627521

- goodsNo | String | 货品编号 | 示例=货品编号1111

- goodsName | String | 货品名称 | 示例=货品名称111

- unitName | String | 单位名称 | 示例=个

- currencyCode | String | 币种code | 示例=CNY

- currencyName | String | 币种名称 | 示例=人民币

- isCurrentActive | Integer | 是否生效(0 = 未生效，1= 生效 ) | 示例=1

- minPrice | BigDecimal | 最低售价（系统默认价格类型） | 示例=10.11

- price1 | BigDecimal | 零售价（系统默认价格类型） | 示例=10.12

- price2 | BigDecimal | 批发价（系统默认价格类型） | 示例=10.11

- price3 | BigDecimal | 会员价（系统默认价格类型） | 示例=10.11

- price4 | BigDecimal | 价格4 | 示例=10.11

- price5 | BigDecimal | 价格5  (总共 price5  -  price51) | 示例=10.11

- id | Long | 价格信息id | 示例=2426857552802252288

- gmtCreate | Date | 新增时间 | 示例=1772503964000

- gmtModified | Date | 修改时间 | 示例=1772503964000

### JSON请求示例

```json

{"unitNames":"1,2,3","currencyCodes":"1,2,3","isDeletes":"0,1","groupId":"4499145120495627521","pageSize":50,"skuNames":"1,2,3","skuIds":"111,222,333","goodsIds":"1,2,3","goodsNos":"1,2,3","goodsNames":"1,2,3","pageIndex":0,"isCurrentActive":1,"cols":"skuId,price1","skuBarcodes":"1,2,3"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":[{"price9":10.11,"price18":10.11,"price19":10.11,"price10":10.11,"price11":10.11,"price12":10.11,"price13":10.11,"price14":10.11,"price15":10.11,"price16":10.11,"price17":10.11,"price7":10.11,"price8":10.11,"isCurrentActive":1,"price5":10.11,"price6":10.11,"price3":10.11,"price50":10.11,"goodsName":"货品名称111","price4":10.11,"price51":10.11,"skuId":"4499145120495627521","price1":10.12,"price2":10.11,"unitName":"个","price43":10.11,"price44":10.11,"price45":10.11,"price46":10.11,"price47":10.11,"price48":10.11,"price49":10.11,"minPrice":10.11,"price40":10.11,"price41":10.11,"price42":10.11,"goodsId":"4499145120495627521","skuName":"规格名","price32":10.11,"price33":10.11,"price34":10.11,"price35":10.11,"currencyName":"人民币","price36":10.11,"price37":10.11,"price38":10.11,"price39":10.11,"price30":10.11,"price31":10.11,"goodsNo":"货品编号1111","price29":10.11,"price21":10.11,"price22":10.11,"price23":10.11,"price24":10.11,"price25":10.11,"price26":10.11,"price27":10.11,"price28":10.11,"skuBarcode":"条码111","currencyCode":"CNY","price20":10.11}],"contextId":"2261582959038792832"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2261582959038792832"},"subCode":"0130020001"}

```

## erp.salesgoodsskuprice.create（创建货品价目（已经存在则修改，根据规格、单位、币种定位））

接口等级：免费接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-09-03 16:08:46.0

说明：创建货品价目（已经存在则修改，根据规格、单位、币种定位）：
通过此接口可以创建、修改货品价目到吉客云的系统。其中公司、部门传吉客云系统的公司、部门的编号。币种不传默认调整人民币。货品根据条码或者外部同步的唯一编号定位。

常见问题：

请求字段数：33；返回字段数：1

### 请求字段

- currencyCode | String | 必填=False | 币种编号 | 示例=CNY

- currencyName | String | 必填=False | 币种名称 | 示例=人民币

- memo | String | 必填=False | 备注 | 示例=备注A

- applyDate | Date | 必填=False | 申请时间 | 示例=2021-06-01 09:45:59

- companyCode | String | 必填=True | 公司编号 | 示例=公司编号A

- departCode | String | 必填=True | 部门名称 | 示例=部门编号A

- applyUserName | String | 必填=True | 申请人姓名 | 示例=张三

- salesGoodsPriceAdjustmentList | Array | 必填=True | 调价货品集合 | 示例=-

- salesGoodsPriceAdjustmentList-rowRemark | String | 必填=False | 备注 | 示例=货品行备注A

- salesGoodsPriceAdjustmentList-price1 | BigDecimal | 必填=False | 零售价 | 示例=2

- salesGoodsPriceAdjustmentList-price2 | BigDecimal | 必填=False | 批发价 | 示例=1

- salesGoodsPriceAdjustmentList-price3 | BigDecimal | 必填=False | 会员价 | 示例=2

- salesGoodsPriceAdjustmentList-minPrice | BigDecimal | 必填=False | 最低售价 | 示例=5

- salesGoodsPriceAdjustmentList-outSkuCode | String | 必填=False | 外部编号(外部编号和条码必传一个，skuBarcode > outSkuCode) | 示例=B0001

- salesGoodsPriceAdjustmentList-skuBarcode | String | 必填=False | 条码(外部编号(外部编号和条码必传一个，skuBarcode > outSkuCode) | 示例=A00001

- salesGoodsPriceAdjustmentList-price4 | BigDecimal | 必填=False | 自定义价格4 | 示例=1

- salesGoodsPriceAdjustmentList-price5 | BigDecimal | 必填=False | 自定义价格5 | 示例=1

- salesGoodsPriceAdjustmentList-price6 | BigDecimal | 必填=False | 自定义价格6 | 示例=1

- salesGoodsPriceAdjustmentList-price7 | BigDecimal | 必填=False | 自定义价格7 | 示例=1

- salesGoodsPriceAdjustmentList-price8 | BigDecimal | 必填=False | 自定义价格8 | 示例=1

- salesGoodsPriceAdjustmentList-price9 | BigDecimal | 必填=False | 自定义价格9 | 示例=1

- salesGoodsPriceAdjustmentList-price10 | BigDecimal | 必填=False | 自定义价格10 | 示例=1

- salesGoodsPriceAdjustmentList-price11 | BigDecimal | 必填=False | 自定义价格11 | 示例=1

- salesGoodsPriceAdjustmentList-price12 | BigDecimal | 必填=False | 自定义价格12 | 示例=1

- salesGoodsPriceAdjustmentList-price13 | BigDecimal | 必填=False | 自定义价格13 | 示例=1

- salesGoodsPriceAdjustmentList-price14 | BigDecimal | 必填=False | 自定义价格14 | 示例=1

- salesGoodsPriceAdjustmentList-price15 | BigDecimal | 必填=False | 自定义价格15 | 示例=1

- salesGoodsPriceAdjustmentList-price16 | BigDecimal | 必填=False | 自定义价格16 | 示例=1

- salesGoodsPriceAdjustmentList-price17 | BigDecimal | 必填=False | 自定义价格17 | 示例=1

- salesGoodsPriceAdjustmentList-price18 | BigDecimal | 必填=False | 自定义价格18 | 示例=1

- salesGoodsPriceAdjustmentList-price19 | BigDecimal | 必填=False | 自定义价格19 | 示例=1

- salesGoodsPriceAdjustmentList-price20 | BigDecimal | 必填=False | 自定义价格20 | 示例=1

- status | Integer | 必填=False | 默认为2，已审核。调价单状态 ：0 待递交 1 待审核 2已审核。根据传入状态判断调价单自动递交/审核设置项，开启则自动递交/自动审核 | 示例=2

### 返回字段

- adjustmentNo | String | 调价单号 | 示例=TJ202106010009

### JSON请求示例

```json

{"companyCode":"公司编号A","memo":"备注A","applyUserName":"张三","salesGoodsPriceAdjustmentList":[{"price9":1,"price18":1,"price19":1,"rowRemark":"货品行备注A","outSkuCode":"B0001","price10":1,"price11":1,"price12":1,"price13":1,"price14":1,"price15":1,"price16":1,"minPrice":5,"price17":1,"price7":1,"price8":1,"price5":1,"skuBarcode":"A00001","price6":1,"price3":2,"price4":1,"price1":2,"price2":1,"price20":1}],"currencyName":"人民币","departCode":"部门编号A","applyDate":"2021-06-01 09:45:59","currencyCode":"CNY"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"adjustmentNo":"TJ202106010009"},"contextId":null},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":null},"subCode":"0130020001"}

```

## erp.goods.updateretailprice（根据外部编码更新货品的固定成本价）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2024-09-23 09:19:08.0

说明：开放平台根据外部编码更新货品的固定成本价。

常见问题：

请求字段数：2；返回字段数：0

### 请求字段

- outSkuCode | String | 必填=False | 外部编码 | 示例=old111

- retailPrice | BigDecimal | 必填=False | 固定成本价 | 示例=123.123

### 返回字段

### JSON请求示例

```json

{"retailPrice":123.123,"outSkuCode":"old111"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{},"contextId":"2045598513362340096"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2045598513362340096"},"subCode":"0130020001"}

```

## erp.goodscate.get（货品分类查询）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2023-12-07 17:19:42.0

说明：货品分类查询

常见问题：

请求字段数：1；返回字段数：8

### 请求字段

- cateCode | String | 必填=False | 分类编号 | 示例=32

### 返回字段

- cateId | String | 分类id | 示例=123

- cateName | String | 分类名称 | 示例=电器

- parentCateId | String | 父级分类id | 示例=231

- isLeaf | String | 是否叶子节点 | 示例=0

- cateCode | String | 分类编号 | 示例=tr

- orderIndex | Integer | 序号 | 示例=1

- usableRange | Integer | 分类使用范围 0-标识全部 1-表示单品 2表示组合装 | 示例=0

- cateFullName | String | 分类全称 | 示例=421

### JSON请求示例

```json

{"cateCode":"32"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":[{"usableRange":"0","cateId":"123","cateFullName":"421","orderIndex":1,"cateName":"电器","isLeaf":"0","parentCateId":"231","cateCode":"tr"}],"contextId":"1834930680499110784"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1834930680499110784"},"subCode":"0130020001"}

```

## erp.brand.get（开放平台货品品牌列表查询）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-01-06 10:18:00.0

说明：货品品牌查询接口

常见问题：

请求字段数：3；返回字段数：5

### 请求字段

- brandNameEn | String | 必填=False | 品牌的英文名 | 示例=LiNing

- brandNameCn | String | 必填=False | 品牌中文名 | 示例=李宁

- needTotal | Integer | 必填=False | 查询总数（ 传1 并且分页pageIndex 传 0 查询总数） | 示例=0

### 返回字段

- brandNameCn | String | 品牌中文名 | 示例=李宁

- brandId | String | 品牌id | 示例=12

- brandNameEn | String | 品牌英文名字 | 示例=LiNing

- brandDesc | String | 品牌描述 | 示例=李宁,中国品牌

- brandCode | String | 品牌编码 | 示例=C0001

### JSON请求示例

```json

{"brandNameEn":"LiNing","brandNameCn":"李宁","needTotal":0}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":[{"brandNameEn":"LiNing","brandDesc":"李宁,中国品牌","brandNameCn":"李宁","brandId":"12","brandCode":"C0001"}],"contextId":"1898744883484721536"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1898744883484721536"},"subCode":"0130020001"}

```

## erp.unit.get（辅助单位查询）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2022-08-03 15:06:16.0

说明：开放平台辅助单位查询对外接口

常见问题：

请求字段数：3；返回字段数：23

### 请求字段

- outSkuCode | String | 必填=False | 外部编码 | 示例=

- skuBarcode | String | 必填=False | 条码 | 示例=

- skuId | String | 必填=False | 规格ID | 示例=

### 返回字段

- goodsId | Long | 货品ID | 示例=

- goodsName | String | 货品名称 | 示例=

- goodsNo | String | 货品编号 | 示例=

- goodsNameEn | String | 货品英文名称 | 示例=

- skuId | Long | 规格ID | 示例=

- skuName | String | 规格名称 | 示例=

- skuBarcode | String | 条码 | 示例=

- skuNo | String | 规格编号 | 示例=

- skuCode | String | 外部条码 | 示例=

- goodsUnits | Array | 辅助单位 | 示例=

- goodsUnits-unitName | String | 个 | 示例=

- goodsUnits-pBaseUnit | Integer | 是否是基础单位 | 示例=

- goodsUnits-baseCountRate | BigDecimal | 基础汇率,默认为1 | 示例=

- goodsUnits-assistCountRate | BigDecimal | 辅助单位转换率,默认为1 | 示例=

- goodsUnits-unitMainBarcode | String | 单位主条码 | 示例=

- goodsUnits-unitWeight | BigDecimal | 单位重量 | 示例=

- goodsUnits-unitWeightUnit | String | 单位重量单位名称 | 示例=

- goodsUnits-baseWeight | BigDecimal | 基础重量 | 示例=

- goodsUnits-unitLength | BigDecimal | 长 | 示例=

- goodsUnits-unitWidth | BigDecimal | 宽 | 示例=

- goodsUnits-unitHeight | BigDecimal | 高 | 示例=

- goodsUnits-unitVolume | BigDecimal | 体积 | 示例=

- goodsUnits-unitVolumeUnit | String | 体积单位 | 示例=

### JSON请求示例

```json

{"skuId":"","outSkuCode":"","skuBarcode":""}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"goodsNo":"","goodsNameEn":"","goodsId":"","skuName":"","goodsUnits":[{"unitWeight":"","unitWidth":"","assistCountRate":"","unitName":"","unitVolume":"","pBaseUnit":"","unitVolumeUnit":"","baseCountRate":"","unitHeight":"","unitLength":"","unitMainBarcode":"","baseWeight":"","unitWeightUnit":""}],"skuNo":"","skuBarcode":"","goodsName":"","skuId":"","skuCode":""},"contextId":null},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":null},"subCode":"0130020001"}

```

## wms.order.basicbatchconfirmsync（批量发货确认(逆向)-同步）

接口等级：标准接口; bSubscription：False; bAuthorized：True; postType：0; 最近发布时间：2024-12-09 11:54:48.0

说明：发货确认

常见问题：

请求字段数：57；返回字段数：5

### 请求字段

- results | Array | 必填=True | 发货信息 | 示例=-

- results-deliveryorderid | String | 必填=True | 仓储系统出库单ID | 示例=13454215727

- results-deliveryorderno | String | 必填=True | 出库单号 | 示例=9193457120563834

- results-deliverytype | String | 必填=True | 出库类型(交易出库=JH_01，换货出库=JH_02，补发出库=JH_03，普通出库单=JH_04，调拨出库=JH_05，B2B出库=JH_06，采购退货出库=JH_07，其他出库=JH_08，自提出库=JH_09，B2C销售订单=JH_10，虚拟出库单=JH_11，唯品出库=JH_12，盘亏出库=JH_13，其他出库=JH_99) | 示例=JH_01

- results-deliverystatus | String | 必填=True | 出库单状态 | 示例=04

- results-ownerorderno | String | 必填=True | 外部订单号 | 示例=9193457120563834

- results-warehousecode | String | 必填=True | 仓库编码 | 示例=04

- results-ownercode | String | 必填=True | 货主编码 | 示例=04

- results-outbizcode | String | 必填=True | 外部业务编码 | 示例=04

- results-confirmtype | String | 必填=True | 支持出库单多次发货 | 示例=特快

- results-confirmtime | String | 必填=True | 订单完成时间 | 示例=2016-09-08 12:00:00

- results-operatorcode | String | 必填=True | 操作员编码 | 示例=023

- results-operatorname | String | 必填=True | 操作员姓名 | 示例=023

- results-operatetime | String | 必填=True | 操作时间 | 示例=2016-09-08 12:00:00

- results-storagefee | BigDecimal | 必填=True | 仓储费用 | 示例=12

- results-isinvoiceflag | Integer | 必填=False | 是否需要发票(需要=Y; 不需要=N) | 示例=1

- results-goods | Array | 必填=True | 商品集合 | 示例=-

- results-goods-name | String | 必填=True | 商品名称 | 示例=茶杯

- results-goods-itemid | String | 必填=True | 仓储系统商品ID | 示例=448122312341

- results-goods-unit | String | 必填=True | 单位 | 示例=个

- results-goods-barcode | String | 必填=False | 商品条形码 | 示例=18888201

- results-goods-inventorytype | String | 必填=True | 库存类型(正品=JH_01，残次=JH_02，机损=JH_03，箱损=JH_04，在途库存=JH_05，样品=JH_06) | 示例=JH_01

- results-goods-planqty | Integer | 必填=True | 应发商品数量 | 示例=12

- results-goods-actualqty | Integer | 必填=True | 实发商品数量 | 示例=12

- results-goods-batchcode | String | 必填=False | 批次编号 | 示例=12

- results-goods-productdate | String | 必填=False | 生产日期 | 示例=2016-09-09

- results-goods-expiredate | String | 必填=False | 过期日期 | 示例=2016-09-09

- results-goods-producecode | String | 必填=False | 生产批号 | 示例=PH1204

- results-goods-batchs | Array | 必填=False | 批次列表 | 示例=-

- results-goods-batchs-batchcode | String | 必填=True | 批次编号 | 示例=PC1234

- results-goods-batchs-productdate | String | 必填=True | 生产日期 | 示例=2016-09-09

- results-goods-batchs-expiredate | String | 必填=True | 过期日期 | 示例=2016-09-09

- results-goods-batchs-producecode | String | 必填=True | 生产批号 | 示例=PH1204

- results-goods-batchs-sncode | String | 必填=True | SN编码 | 示例=20160909

- results-goods-batchs-inventorytype | String | 必填=True | 库存类型(正品=JH_01，残次=JH_02，机损=JH_03，箱损=JH_04，在途库存=JH_05，样品=JH_06) | 示例=PH1204

- results-goods-batchs-actualqty | Integer | 必填=True | 实发数量 | 示例=12

- results-goods-subdeliveryorderid | String | 必填=True | 仓库拆单子发货单号 | 示例=WI1234

- results-goods-outDetailId | String | 必填=True | 外部明细ID | 示例=123456789012345678

- results-goods-outSkuCode | String | 必填=True | 外部货品唯一编码 | 示例=2323232323223

- results-goods-snlist | Array | 必填=True | SN列表 | 示例=JH_01,JD_02

- results-goods-sncode | String | 必填=True | SN码 | 示例=WI1234

- results-invoice | Object | 必填=True | 发票信息 | 示例=-

- results-invoice-invoiceno | String | 必填=True | 发票号 | 示例=S12345171

- results-invoice-invoicetype | String | 必填=True | 发票类型(普通发票=JH_01，增值税发票=JH_02，专业发票=JH_03) | 示例=JH_01

- results-invoice-invoicetitle | String | 必填=True | 发票抬头 | 示例= 杭州笛佛有限公司

- results-invoice-invoicecontent | String | 必填=True | 发票内容 | 示例=电脑设备

- results-invoice-invoiceacount | BigDecimal | 必填=True | 发票金额 | 示例=5288.0

- results-invoice-taxnumber | String | 必填=True | 发票税号 | 示例=T5418742315412

- results-invoice-invoicedetail | String | 必填=True | 发票明细 | 示例=电脑配件

- results-invoice-bankname | String | 必填=True | 开户银行名称 | 示例=城西支行

- results-invoice-bankaccount | String | 必填=True | 开户银行账户 | 示例=6225443645454157

- results-packagelist | Array | 必填=True | 包裹信息 | 示例=-

- results-packageWeight | BigDecimal | 必填=True | 包裹重量 | 示例=12

- results-packagelist-logisticscode | String | 必填=True | 物流公司编码 | 示例=SF

- results-packagelist-logisticsname | String | 必填=True | 物流公司名称 | 示例=顺丰

- results-packagelist-expresscode | String | 必填=True | 运单号 | 示例=Y1234

- results-packagelist-packagecode | String | 必填=True |  包裹编号 | 示例=LG1234

### 返回字段

- deliveryOrderResponseList | Array | 创建发货单返回结构体集合 | 示例=-

- deliveryOrderResponseList-orderNo | String | WMS发货单编号 | 示例=S201807250002 

- deliveryOrderResponseList-erporderNo | String | 外部ERP单号 | 示例=JY201807250056 

- deliveryOrderResponseList-errorMsg | String | 失败原因 | 示例=网路异常

- deliveryOrderResponseList-isSuccess | String | 是否成功标识 | 示例=false

### JSON请求示例

```json

{"results":[{"packageWeight":12,"deliveryorderid":"13454215727","goods":[{"subdeliveryorderid":"WI1234","productdate":"2016-09-09","producecode":"PH1204","snlist":"JH_01,JD_02","batchcode":"12","expiredate":"2016-09-09","outSkuCode":"2323232323223","itemid":"448122312341","barcode":"18888201","planqty":12,"outDetailId":"123456789012345678","actualqty":12,"batchs":[{"productdate":"2016-09-09","producecode":"PH1204","batchcode":"PC1234","expiredate":"2016-09-09","actualqty":12,"sncode":"20160909","inventorytype":"PH1204"}],"unit":"个","sncode":"WI1234","inventorytype":"JH_01","name":"茶杯"}],"ownerorderno":"9193457120563834","operatetime":"2016-09-08 12:00:00","confirmtime":"2016-09-08 12:00:00","deliverytype":"JH_01","operatorcode":"023","warehousecode":"04","packagelist":[{"logisticsname":"顺丰","packagecode":"LG1234","logisticscode":"SF","expresscode":"Y1234"}],"isinvoiceflag":1,"storagefee":12,"deliveryorderno":"9193457120563834","confirmtype":"特快","outbizcode":"04","ownercode":"04","deliverystatus":"04","invoice":{"invoicedetail":"电脑配件","invoiceacount":5288.0,"bankaccount":"6225443645454157","invoicetype":"JH_01","invoicecontent":"电脑设备","taxnumber":"T5418742315412","invoicetitle":" 杭州笛佛有限公司","bankname":"城西支行","invoiceno":"S12345171"},"operatorname":"023"}]}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"deliveryOrderResponseList":[{"orderNo":"S201807250002 ","erporderNo":"JY201807250056 ","errorMsg":"网路异常","isSuccess":"false"}]},"contextId":"2010274983674020480"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2010274983674020480"},"subCode":"0130020001"}

```

## oms.trade.confirm（发货确认(逆向)）

接口等级：免费接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2026-01-28 17:15:27.0

说明：将订单发货确认信息回传给外部系统

常见问题：

请求字段数：22；返回字段数：0

### 请求字段

- order | Object | 必填=False | 单据信息 | 示例=-

- order-tradeNo | String | 必填=False | 订单编号 | 示例=JY0001

- order-stockOutTime | Date | 必填=False | 出库时间 | 示例=2025-01-01 00:00:00

- goods | Array | 必填=False | 货品明细 | 示例=-

- goods-goodsNo | String | 必填=False | 货品编号 | 示例=001

- goods-skuBarcode | String | 必填=False | 货品条码 | 示例=001

- goods-skuName | String | 必填=False | 货品规格 | 示例=默认

- goods-unit | String | 必填=False | 单位 | 示例=克

- goods-sendCount | BigDecimal | 必填=False | 发货数量 | 示例=1

- goods-batchInfo | Array | 必填=False | 批次信息 | 示例=-

- goods-batchInfo-productDate | Date | 必填=False | 生产日期 | 示例=2025-01-01 00:00:00

- goods-batchInfo-expireDate | Date | 必填=False | 过期日期 | 示例=2025-01-01 00:00:00

- goods-batchInfo-sendCount | BigDecimal | 必填=False | 批次数量 | 示例=1

- goods-batchInfo-batchNo | String | 必填=False | 批次号 | 示例=001

- packages | Array | 必填=False | 包裹明细 | 示例=-

- packages-isMainlogistic | Integer | 必填=False | 是否为母单号 1是 0否 | 示例=0

- packages-logisticId | Long | 必填=False | 物流id | 示例=1

- packages-logisticName | String | 必填=False | 物流名称 | 示例=申通

- packages-logisticCode | String | 必填=False | 吉客云物流编码 | 示例=ST

- packages-expressCode | String | 必填=False | 快递公司编码 | 示例=ST

- packages-expressName | String | 必填=False | 快递公司名称 | 示例=申通

- packages-logisticNo | String | 必填=False | 物流单号 | 示例=1

### 返回字段

### JSON请求示例

```json

[{"goods":[{"goodsNo":"001","batchInfo":[{"batchNo":"001","sendCount":1,"productDate":"2025-01-01 00:00:00","expireDate":"2025-01-01 00:00:00"}],"sendCount":1,"skuName":"默认","unit":"克","skuBarcode":"001"}],"packages":[{"isMainlogistic":0,"expressName":"申通","logisticName":"申通","expressCode":"ST","logisticId":"1","logisticCode":"ST"}],"order":{"tradeNo":"JY0001","stockOutTime":"2025-01-01 00:00:00"}}]

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{},"contextId":"2229118837749614720"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2229118837749614720"},"subCode":"0130020001"}

```

## oms.trade.fullinfoget（销售单查询）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2026-05-12 17:32:58.0

说明：1、销售单查询根据游标(scrollId)分页查询参数的特殊说明:第一次查询入参增加scrollId="",并在fields字段中添加scrollId字段,在下一次查询时需要将上次查询响应的游标值当做入参去请求下一页的数据；
<br/>
2、部分列表字段fields填写说明详见：https://s.jkyun.biz/2jWhg8v； 
<br/>
3、开放平台销售单取数核对方式可参考：https://s.jkyun.biz/T5x1lE5;    
<br/>
4，销售单号、网店订单号、分批发货申请单号、修改时间、创建时间、审核时间、发货时间、完成时间、下单时间必传其一，起止时间不能超过7天。

常见问题：1、销售数据对接需要确定是否包含淘系订单（淘宝、天猫等淘系店铺产生的单据），如果包含淘系订单数据则需要确定客户是否具备奇门资质或者是否具备能力申请奇门资质。 具体的申请过程可以参看以下文档 https://s.jkyun.biz/0Wuqdit 对接奇门API访问吉客云开放平台。 
<br/>
2、开通奇门资质只是为了获取销售订单的货品金额、货品数量、货品编号等货品数据，对于收货人信息仍旧无法获取。
<br/>

请求字段数：51；返回字段数：299

### 请求字段

- startModified | Date | 必填=False | 最后修改时间（起始） | 示例=2024-06-05 11:26:00

- endModified | Date | 必填=False | 最后修改时间（截止） | 示例=2024-06-11 11:26:00

- tradeNo | String | 必填=False | 销售单号，多个用半角逗号分隔 | 示例=JY202406050002

- tradeIds | Array | 必填=False | 订单Id | 示例=[2307317872088616192,2325498819791326465]

- pageSize | Integer | 必填=False | 每页记录数，默认50，最大200 | 示例=5

- startCreated | Date | 必填=False | 创建时间（起始） | 示例=2024-06-05 11:26:00

- endCreated | Date | 必填=False | 创建时间（截止） | 示例=2024-06-11 11:26:00

- startAuditTime | Date | 必填=False | 审核时间（起始） | 示例=2024-06-05 11:26:00

- endAuditTime | Date | 必填=False | 审核时间（截止） | 示例=2024-06-11 11:26:00

- startConsignTime | Date | 必填=False | 发货时间（起始） | 示例=2024-10-15 11:26:00

- endConsignTime | Date | 必填=False | 发货时间（截止） | 示例=2024-10-19 11:26:00

- tradeStatus | Integer | 必填=False | 销售单状态（1010：待审核；1020：审核中；1030：预售；1050：待复核；2000：备货等待；2010：备货等待等补货；2020：服务等待；2030：备货等待等生产；2040：采购等待；3010：虚拟发货；4110：待发货待递交；4111：待发货递交中；4112：待发货已递交；4113：待发货-递交失败；4121：待发货-取消中；4122：待发货已取消；4123：待发货取消失败；4130：待发货部分发货；4040：代销发货待递交；4041：代销发货已递交；5010：已取消；5020：已取消被合并；5030：已取消被拆分；6000：发货在途；9090：已完成） | 示例=9090

- sourceTradeNos | String | 必填=False | 网店订单号 | 示例=D241015171823K00002Z01

- shopIds | Array | 必填=False | 店铺id | 示例=["1647727244400592896","1647727244400592886"]

- fields | String | 必填=True | 需要返回的字段列表，多个字段用半角逗号分隔，可选值为返回示例中能看到的所有字段。tradeNo:订单编号,goodsDetail.outerId:商品编码,pickUpCode:取货码,expense.expenseFee打包费,expense.expenseItemName费用名称,billDate:对账时间（得传对账时间起止),goodsPlatDiscountFee:货品平台优惠 | 示例=tradeNo,orderNo,shopName,companyName,warehouseName,logisticName,mainPostid,goodsDetail.goodsNo,flagNames,columnExt,sourceAfterNo,goodsDetail.outerId,pickUpCode,expense.expenseFee,expense.expenseItemName,billDate,goodsPlatDiscountFee,goodsDetail.shareOrderDiscountFee,goodsDetail.shareOrderPlatDiscountFee,customizeGoodsColumn9,goodsDetail.goodsId,goodsDetail.sellCount,goodsDetail.needProcessCount,goodsDetail.baseUnitSellCount,goodsDetail.assessmentCost,goodsDetail.compassSourceContentTypem,sourceTradeNo,shopId,warehouseId,scrollId

- isTableSwitch | Integer | 必填=False | 是否分表查询（1：日常表数据；0：否；2：归档数据）（不支持查询深度归档，不传默认为1） | 示例=1

- startSigningTime | Date | 必填=False | 订单签收时间（起始） | 示例=2024-06-05 11:26:00

- endSigningTime | Date | 必填=False | 订单签收时间（截止） | 示例=2024-06-11 11:26:00

- warehouseIds | Array | 必填=False | 仓库Id | 示例=["1718178122057024640","1718178122057024640"]

- isDelete | String | 必填=False | 是否删除（0：否；1：是） | 示例=0

- scrollId | String | 必填=False | 游标id。默认为空，入参增加scrollId=""优先游标方式查询（分页pageIndx失效）。接口返回scrollId字段，下次调用添加到请求参数。 | 示例=e435cb66390bb1eac99aa5755805f9f7

- tradeType | Integer | 必填=False | 销售单类型（1：零售业务；2：代发货（来自分销商）；3：预售订单；4：周期性订购；5：代销售（供货商发货）；6：现款现货；7：售后发货；8：售后退货；9：批发业务（B2B）；10：试销业务；11：错漏调整；12：仅退款；13：销售返利；14：大B2B业务；15物流买赔；16销售对账差异 91：自定义1；92：自定义2；93：自定义3...100：自定义10） | 示例=1

- tradeTypeList | Array | 必填=False | 销售单类型列表（1：零售业务；2：代发货（来自分销商）；3：预售订单；4：周期性订购；5：代销售（供货商发货）；6：现款现货；7：售后发货；8：售后退货；9：批发业务（B2B）；10：试销业务；11：错漏调整；12：仅退款；13：销售返利；14：大B2B业务；15物流买赔；16销售对账差异 91：自定义1；92：自定义2；93：自定义3...100：自定义10） | 示例=[1,2]

- mainPostId | String | 必填=False | 物流单号 | 示例=

- mainPostIdList | String | 必填=False | 物流单号列表 | 示例=

- startPlatCompleteTime | Date | 必填=False | 平台完成时间（起始） | 示例=2024-09-09 11:27:25

- endPlatCompleteTime | Date | 必填=False | 平台完成时间（截止） | 示例=2024-09-15 11:27:25

- logisticId | String | 必填=False | 物流公司id | 示例=1068646551979302016

- logisticIdList | Array | 必填=False | 物流id数组 | 示例=[388942822334274688,1518158299225922688,1611460754588861952]

- startNotifyPickTime | Date | 必填=False | 通知仓库配货时间（起始） | 示例=2025-12-01 00:00:00

- endNotifyPickTime | Date | 必填=False | 通知仓库配货时间（截止） | 示例=2025-12-16 23:59:59

- startCompleteTime | Date | 必填=False | 订单完成时间（起始） | 示例=2025-12-01 00:00:00

- endCompleteTime | Date | 必填=False | 订单完成时间（截止） | 示例=2025-12-16 23:59:59

- startConfirmTime | Date | 必填=False | 订单确认时间（起始） | 示例=2025-12-01 00:00:00

- endConfirmTime | Date | 必填=False | 订单确认时间（截止） | 示例=2025-12-16 23:59:59

- startBillDate | Date | 必填=False | 记账时间（起始） | 示例=2025-12-01 00:00:00

- endBillDate | Date | 必填=False | 记账时间（截止） | 示例=2025-12-16 23:59:59

- startSettleTime | Date | 必填=False | 结算时间（起始） | 示例=2025-12-01 00:00:00

- endSettleTime | Date | 必填=False | 结算时间（截止） | 示例=2025-12-16 23:59:59

- startFinReceiptTime | Date | 必填=False | 对账时间（起始） | 示例=2025-12-01 00:00:00

- endFinReceiptTime | Date | 必填=False | 对账时间（截止） | 示例=2025-12-16 23:59:59

- startTradeTime | Date | 必填=False | 下单时间（开始） | 示例=2025-12-01 00:00:00

- endTradeTime | Date | 必填=False | 下单时间（截止） | 示例=2025-12-16 23:59:59

- tradeStatusList | Array | 必填=False | 销售单状态列表 | 示例=[1010, 1050, 6000]

- customerTradeNos | String | 必填=False | 终端网店单号，多个用半角逗号隔开 | 示例=“1002663531489534600,1002663531489534601”

- currentMaxId | Long | 必填=False | 使用当前最大id来判断下次查询的 | 示例=123456789

- tradeDeliveryNo | String | 必填=False | 分批发货单号，多个用半角逗号分隔 | 示例=“JY202512160001,JY202512160002”

- isBillCheck | Integer | 必填=False | 对账状态 | 示例=1

- isReturnPddData | Integer | 必填=False | 是否返回拼多多数据 | 示例=1

- isPddQuery | Integer | 必填=False | 查询来源：拼多多平台 | 示例=1

- tradeTime | Date | 必填=False | 下单时间 | 示例=2025-12-01 10:30:00

### 返回字段

- trades | Array | 销售单 | 示例=

- trades-checkTotal | BigDecimal | 对账金额 | 示例=0

- trades-tradeNo | String | 订单编号 | 示例=

- trades-otherFee | BigDecimal | 其它费用 | 示例=0

- trades-chargeCurrency | String | 结算币种 | 示例=人民币

- trades-accountName | String | 收款账户 | 示例=支付宝账号

- trades-payType | Integer | 支付方式（1：支付宝；2：财付通；3：微信支付；4：银联支付；5：盛付通；6：其它；7：现金；8：储值卡；9：扫码付；10：挂账；11：诺诺支付；16：易付宝；27：通联支付；32：有赞支付；33：汇付支付；35：商盟支付；36：易宝支付；37：汇聚支付；38：合利宝支付） | 示例=1

- trades-payNo | String | 支付单号 | 示例=201906000000000000000

- trades-sellerMemo | String | 客服备注 | 示例=

- trades-buyerMemo | String | 买家备注 | 示例=

- trades-goodsDetail | Array | 货品详情 | 示例=

- trades-goodsDetail-goodsNo | String | 货品编号 | 示例=goodsDetail.goodsNo

- trades-goodsDetail-goodsName | String | 货品名称 | 示例=goodsDetail.goodsName

- trades-goodsDetail-specName | String | 规格名称 | 示例=

- trades-goodsDetail-barcode | String | 条码 | 示例=

- trades-goodsDetail-sellCount | BigDecimal | 数量 | 示例=10

- trades-goodsDetail-unit | String | 单位 | 示例=

- trades-goodsDetail-sellPrice | BigDecimal | 单价 | 示例=2

- trades-goodsDetail-refundStatus | Integer | 0：无退款1：买家申请退款 2：商家同意退款 3：退款关闭 4：卖家拒绝退款 5：付款以前 6：卖家已经同意退款 7：买家已经退货 8：买家已经申请退款 9：货品部分退款 | 示例=field需要加 goodsDetail.refundStatus

- trades-goodsDetail-sellTotal | BigDecimal | 总金额 | 示例=200

- trades-goodsDetail-cost | BigDecimal | 货品成本 | 示例=0

- trades-goodsDetail-discountTotal | BigDecimal | 抵扣金额 | 示例=0

- trades-goodsDetail-discountPoint | Integer | 抵扣积分 | 示例=0

- trades-goodsDetail-taxFee | BigDecimal | 税额 | 示例=0

- trades-goodsDetail-shareFavourableFee | BigDecimal | 分摊金额 | 示例=0

- trades-goodsDetail-estimateWeight | BigDecimal | 预估重量 | 示例=0

- trades-goodsDetail-goodsMemo | String | 货品备注 | 示例=

- trades-goodsDetail-cateName | String | 货品分类 | 示例=

- trades-goodsDetail-brandName | String | 品牌 | 示例=

- trades-goodsDetail-goodsTags | String | 货品标签 | 示例=

- trades-goodsDetail-isFit | Integer | 组合装标记 | 示例=0

- trades-goodsDetail-isGift | Integer | 赠品标记（0：否；1：是） | 示例=0

- trades-goodsDetail-discountFee | BigDecimal | 优惠 | 示例=0

- trades-goodsDetail-taxRate | BigDecimal | 税率 | 示例=0

- trades-goodsDetail-estimateGoodsVolume | BigDecimal | 预估体积（单个货品） | 示例=0

- trades-goodsDetail-isPresell | Integer | 是否预售货品标记（0：否；1：是） | 示例=0

- trades-goodsDetail-customerPrice | BigDecimal | 终端销售单价 | 示例=1

- trades-goodsDetail-customerTotal | BigDecimal | 终端销售金额 | 示例=1

- trades-goodsDetail-tradeGoodsNo | String | 交易编号 | 示例=

- trades-goodsDetail-tradeGoodsName | String | 交易名称 | 示例=

- trades-goodsDetail-tradeGoodsSpec | String | 交易规格 | 示例=

- trades-goodsDetail-tradeGoodsUnit | String | 交易单位 | 示例=

- trades-goodsDetail-sourceSubtradeNo | String | 网店子订单号 | 示例=

- trades-goodsDetail-platCode | String | 平台代码 | 示例=

- trades-goodsDetail-platGoodsId | String | 商品链接id | 示例=

- trades-goodsDetail-subTradeId | String | 商品明细id（唯一） | 示例=

- trades-goodsDetail-goodsDelivery | Array | 货品发货批次明细 | 示例=

- trades-goodsDetail-goodsDelivery-sendCount | BigDecimal | 数量 | 示例=1

- trades-goodsDetail-goodsDelivery-productionDate | String | 生产日期（取货品批次中维护的数据） | 示例=fields需要加：goodsDetail.specId,goodsDelivery.batchNo

- trades-goodsDetail-goodsDelivery-expirationDate | String | 到期日期（取货品批次中维护的数据） | 示例=fields需要加：goodsDetail.specId,goodsDelivery.batchNo

- trades-goodsDetail-goodsDelivery-batchNo | String | 批次号 | 示例=goodsDelivery.batchNo

- trades-goodsDetail-goodsDelivery-expireDate | String | 到期日期（取销售单中的数据） | 示例=2023-06-29 00:00:00

- trades-goodsDetail-goodsDelivery-productDate | String | 生产日期（取销售单中的数据） | 示例=2020-06-29 00:00:00

- trades-goodsDetail-platAuthorId | String | 平台主播id | 示例=达人id

- trades-goodsDetail-platAuthorName | String | 平台主播名称 | 示例=达人名称

- trades-goodsDetail-isPlatGift | String | 平台赠品标记 | 示例=1

- trades-goodsDetail-goodsPlatDiscountFee | BigDecimal | 货品平台优惠 | 示例=111

- trades-goodsDetail-tradeOrderGoodsDiscountInfoDtoList | String | 货品平台优惠明细 | 示例=-

- trades-goodsDetail-tradeOrderGoodsDiscountInfoDtoList-discountFee | BigDecimal | 优惠金额 | 示例=1

- trades-goodsDetail-tradeOrderGoodsDiscountInfoDtoList-discountName | String | 优惠金额名称 | 示例=积分

- trades-goodsDetail-shareFavourableAfterFee | BigDecimal | 分摊后金额 | 示例=1

- trades-goodsDetail-divideSellTotal | BigDecimal | 实付金额 | 示例=1

- trades-goodsDetail-shareOrderDiscountFee | BigDecimal | 分摊后优惠 | 示例=1

- trades-goodsDetail-shareOrderPlatDiscountFee | BigDecimal | 分摊后平台补贴 | 示例=1

- trades-goodsDetail-sourceTradeNo | String | 网店主订单号 | 示例=111

- trades-goodsDetail-actualSendCount | BigDecimal | 实发数（fields加actualSendCount） | 示例=12

- trades-goodsDetail-platSkuId | String | 平台商品链接skuId | 示例=-

- trades-goodsDetail-customerTradeNo | String | 终端网店订单号 | 示例=2464814

- trades-goodsDetail-customerSubtradeNo | String | 终端网店子订单号 | 示例=246481466

- trades-goodsDetail-PlatCustomData | String | 平台定制信息 | 示例=-

- trades-goodsDetail-assessmentCostLocal | BigDecimal | 考核成本 | 示例=5.36

- trades-goodsDetail-assessmentGrossProfitLocal | BigDecimal | 考核毛利 | 示例=10.59

- trades-goodsDetail-assessmentGrossProfitPercent | String | 考核毛利率 | 示例=63.98%

- trades-goodsDetail-goodsCompassSourceContentType | String | 货品级流量题材（直播带货、橱窗、短视频） | 示例=直播带货

- trades-goodsDetail-goodsSeller | String | 货品业务员 | 示例=张三

- trades-goodsDetail-inventoryWarehouseId | String | 货品逻辑仓id | 示例=176487912535445678

- trades-goodsDetail-inventoryWarehouseName | String | 货品逻辑仓名称 | 示例=杭州仓

- trades-goodsDetail-specId | String | 规格id | 示例=

- trades-goodsDetail-goodsId | String | 货品id | 示例=

- trades-goodsDetail-outerId | String | 外部id | 示例=

- trades-goodsDetail-apiType | String | 渠道类型 | 示例=

- trades-goodsDetail-tradeId | String | 销售单id | 示例=

- trades-goodsDetail-skuImgUrl | String | 规格id | 示例=

- trades-goodsDetail-needProcessCount | BigDecimal | 需备货数量  | 示例=0

- trades-goodsDetail-goodsFlagIds | String | 货品标记id | 示例=5100

- trades-goodsDetail-goodsFlagNames | String | 货品标记名称 | 示例=仓内加工

- trades-appendMemo | String | 追加备注 | 示例=

- trades-tradeFrom | Integer | 订单来源（1：网店下载；2：手工新建；3：订单导入；4：吉商城；6：售后；7：门店；8：分销；9：吉链采购；10：吉链分销；11：吉商城分销；12：奇门分销；13：销售返利；14：门店补货；15：吉秘机器人；16：调拨；17：吉客发；18：开放平台；19：生产推单；20：吉秘助手；21：意向单；22：吉会员；23：账单；24：销售合同；25：商机；26：导购开单；27：寄售结算；28：货主收费；99：WMS创建） | 示例=1

- trades-register | String | 登记人 | 示例=

- trades-seller | String | 业务员 | 示例=

- trades-auditor | String | 审核人 | 示例=

- trades-reviewer | String | 复核人 | 示例=

- trades-estimateWeight | BigDecimal | 预估重量 | 示例=1000

- trades-packageWeight | BigDecimal | 包裹重量 | 示例=1050

- trades-tradeCount | BigDecimal | 订单总数量 | 示例=4

- trades-goodsTypeCount | BigDecimal | 商品样数 | 示例=2

- trades-freezeReason | String | 冻结原因 | 示例=

- trades-abnormalDescription | String | 问题单具体描述 | 示例=

- trades-onlineTradeNo | String | 网店订单号 | 示例=

- trades-goodslist | String | 货品摘要 | 示例=

- trades-gmtCreate | Date | 创建时间 | 示例=2019-06-05 11:26:00

- trades-gmtModified | Date | 最后修改时间 | 示例=2019-06-05 11:26:00

- trades-stockoutNo | String | 出库单号 | 示例=CK201906050001

- trades-confirmTime | Date | 确认时间 | 示例=2019-06-05 11:26:00

- trades-departName | String | 部门名称 | 示例=

- trades-lastShipTime | Date | 承诺发货时间 | 示例=2019-06-05 11:26:00

- trades-payStatus | Integer | 付款状态（0：未付款；5：部分付款:；9：已付款） | 示例=0

- trades-chargeCurrencyCode | String | 结算币种编码 | 示例=CNY

- trades-chargeExchangeRate | BigDecimal | 结算汇率 | 示例=0.7868

- trades-tradeStatus | Integer | 销售单状态（1010：待审核；1020：审核中；1030：预售；1050：待复核；2000：备货等待；2010：备货等待等补货；2020：服务等待；2030：备货等待等生产；2040：采购等待；3010：虚拟发货；4110：待发货待递交；4111：待发货递交中；4112：待发货已递交；4113：待发货-递交失败；4121：待发货-取消中；4122：待发货已取消；4123：待发货取消失败；4130：待发货部分发货；4040：代销发货待递交；4041：代销发货已递交；5010：已取消；5020：已取消被合并；5030：已取消被拆分；6000：发货在途；9090：已完成） | 示例=1010

- trades-grossProfit | BigDecimal | 毛利 | 示例=100

- trades-estimateVolume | BigDecimal | 订单预估体积 | 示例=0

- trades-customerTypeName | String | 客户类型 | 示例=

- trades-customerGradeName | String | 客户等级 | 示例=

- trades-customerTags | String | 客户标签 | 示例=

- trades-customerCode | String | 客户编号 | 示例=

- trades-customerDiscount | BigDecimal | 折扣 | 示例=1

- trades-specialReminding | String | 特别提醒 | 示例=

- trades-blackList | Integer | 黑名单 | 示例=0

- trades-tradeTime | Date | 下单时间 | 示例=2019-06-05 11:26:00

- trades-country | String | 国家 | 示例=

- trades-state | String | 省 | 示例=

- trades-city | String | 城市 | 示例=

- trades-district | String | 区县 | 示例=

- trades-town | String | 街道 | 示例=

- trades-zip | String | 邮编 | 示例=

- trades-payTime | Date | 支付时间 | 示例=2019-06-05 11:26:00

- trades-countryCode | String | 国家编码 | 示例=

- trades-cityCode | String | 城市编码 | 示例=

- trades-invoiceType | Integer | 发票类型（0:无；1:增值税电子普通发票；2:增值税普通发票；3:增值税专用发票；4:增值税电子专用发票；5:普通发票（全电）；6:专用发票（全电）） | 示例=0

- trades-payerName | String | 购方名称 | 示例=

- trades-payerRegno | String | 购方税号 | 示例=

- trades-payerBankAccount | String | 购方开户行及帐号 | 示例=

- trades-payerPhone | String | 购方电话 | 示例=

- trades-auditTime | Date | 审核时间 | 示例=2019-06-05 11:26:00

- trades-payerAddress | String | 购方地址 | 示例=

- trades-invoiceNo | String | 发票号码 | 示例=

- trades-invoiceCode | String | 发票代码 | 示例=

- trades-invoiceStatus | Integer | 发票开具状态 | 示例=1

- trades-payerBankName | String | 购方开户行 | 示例=

- trades-preTypedetail | String | 预定类别描述 | 示例=

- trades-firstPayment | BigDecimal | 付首款金额 | 示例=0

- trades-finalPayment | BigDecimal | 付尾款金额 | 示例=0

- trades-firstPaytime | Date | 付首款时间 | 示例=2019-06-05 11:26:00

- trades-finalPaytime | Date | 付尾款时间 | 示例=2019-06-05 11:26:00

- trades-reviewTime | Date | 复核时间 | 示例=2019-06-05 11:26:00

- trades-activationTime | Date | 激活时间 | 示例=2019-06-05 11:26:00

- trades-customerTotalFee | BigDecimal | 终端货款合计 | 示例=10

- trades-customerDiscountFee | BigDecimal | 终端优惠 | 示例=10

- trades-notifyPickTime | Date | 通知仓库发货时间 | 示例=2019-06-05 11:26:00

- trades-consignTime | Date | 发货时间 | 示例=2019-06-05 11:26:00

- trades-orderNo | String | 发货单单号 | 示例=

- trades-customerPostFee | BigDecimal | 终端应收邮资 | 示例=1

- trades-shopId | Long | 店铺id | 示例=123

- trades-shopName | String | 店铺名称 | 示例=

- trades-tradeOrderPayList | Array | 订单支付详情 | 示例=

- trades-tradeOrderPayList-chargeType | Integer | 结算方式（1：担保交易；2：银行收款；3：现金收款；4：货到付款；5：欠款计应收；6：客户预存款；7：多种结算；8：退换货冲抵；9：电子钱包） | 示例=1

- trades-tradeOrderPayList-chargeCurrency | String | 结算币种 | 示例=

- trades-tradeOrderPayList-chargeAccount | String | 收款帐户 | 示例=

- trades-tradeOrderPayList-accountName | String | 收款账户名称 | 示例=

- trades-tradeOrderPayList-payType | Integer | 支付方式（1：支付宝；2：财付通；3：微信支付；4：银联支付；5：盛付通；6：其它；7：现金；8：储值卡；9：扫码付；10：挂账；11：诺诺支付；16：易付宝；27：通联支付；32：有赞支付；33：汇付支付；35：商盟支付；36：易宝支付；37：汇聚支付；38：合利宝支付） | 示例=1

- trades-tradeOrderPayList-payNo | String | 支付单号 | 示例=

- trades-tradeOrderPayList-payment | BigDecimal | 支付金额 | 示例=123

- trades-tradeOrderPayList-chargeCurrencyCode | String | 结算币种编码 | 示例=

- trades-tradeOrderPayList-chargeExchangeRate | BigDecimal | 结算汇率 | 示例=12

- trades-customerPayment | BigDecimal | 终端应收合计 | 示例=12

- trades-companyName | String | 公司名称 | 示例=

- trades-tradeOrderColumnExt | Object | 销售单自定义字段 | 示例=fields添加columnExt

- trades-tradeOrderColumnExt-tradeId | Long | 系统编码 | 示例=123

- trades-tradeOrderColumnExt-customizeTradeColumn1 | String | 自定义字段1 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn2 | String | 自定义字段2 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn3 | String | 自定义字段3 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn4 | String | 自定义字段4 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn5 | String | 自定义字段5 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn6 | String | 自定义字段6 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn7 | String | 自定义字段7 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn8 | String | 自定义字段8 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn9 | String | 自定义字段9 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn10 | String | 自定义字段10 | 示例=

- trades-tradeOrderColumnExt-customizeTradeColumn23 | String | 自定义字段23 | 示例=

- trades-isBillCheck | Integer | 对账状态（1：对账；其他：未对账） | 示例=1

- trades-warehouseCode | String | 仓库编码 | 示例=

- trades-warehouseName | String | 仓库名称 | 示例=

- trades-logisticName | String | 物流名称 | 示例=

- trades-tradeId | Long | 系统编码 | 示例=123

- trades-billDate | Date | 对账时间 | 示例=2019-06-05 11:26:00

- trades-logisticType | Integer | 配送方式（1：普通快递；2：上门自提；3：门店配送；5：无需配送； 6：线下配送；7：自有物流 ） | 示例=1

- trades-mainPostid | String | 物流单号 | 示例=1000111

- trades-tradeType | Integer | 订单类型 | 示例=0

- trades-totalFee | BigDecimal | 商品金额 | 示例=200

- trades-taxFee | BigDecimal | 税额 | 示例=0

- trades-receivedPostFee | BigDecimal | 应收邮资 | 示例=12

- trades-discountFee | BigDecimal | 优惠金额 | 示例=10

- trades-payment | BigDecimal | 应收金额 | 示例=190

- trades-couponFee | BigDecimal | 平台优惠 | 示例=0

- trades-receivedTotal | BigDecimal | 已收金额 | 示例=190

- trades-postFee | BigDecimal | 预估邮资 | 示例=0

- trades-isTableSwitch | Integer | 是否分表查询 | 示例=1

- trades-completeTime | Date | 平台完成时间 | 示例=2020-01-01 00:00:00

- trades-shopcode | String | 店铺编码 | 示例=-

- trades-signingTime | Date | 签收时间 | 示例=2022-01-07 15:30:46

- trades-goodsSerial | Array | 序列号 | 示例=[]

- trades-goodsSerial-subTradeId | Long | 子订单号 | 示例=123123123

- trades-goodsSerial-skuId | Long | skuId | 示例=123123

- trades-goodsSerial-serialNo | String | 序列号 | 示例=123213

- trades-goodsSerial-serialNo2 | String | 序列号2 | 示例=123456

- trades-goodsSerial-batchNo | String | 批次号 | 示例=1234

- trades-otherPaymentFees | Array | 其他应收 | 示例=[]

- trades-otherPaymentFees-expenseFee | BigDecimal | 费用（需要在fields中加expense.expenseFee） | 示例=12

- trades-otherPaymentFees-expenseItemName | String | 费用名称 （需要在fields中加expense.expenseItemName） | 示例=-

- trades-tradeOrderGoodsColumnExts | Array | 货品自定义字段信息，fields参数中添加goodsDetail.goodsId和货品自定义字段对应的字段名 | 示例=-

- trades-tradeOrderGoodsColumnExts-subTradeId | Long | 订单货品唯一id | 示例=123

- trades-tradeOrderGoodsColumnExts-tradeId | Long | 订单id | 示例=132

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn1 | String | fields要加customizeGoodsColumn1 | 示例=货品自定义字段1

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn2 | String | fields要加customizeGoodsColumn2 | 示例=货品自定义参数2

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn3 | String | fields要加customizeGoodsColumn3 | 示例=货品自定义参数3

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn4 | String | fields要加customizeGoodsColumn4 | 示例=货品自定义参数4

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn5 | String | fields要加customizeGoodsColumn5 | 示例=货品自定义参数5

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn6 | String | fields要加customizeGoodsColumn6 | 示例=货品自定义参数6

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn7 | String | fields要加customizeGoodsColumn7 | 示例=货品自定义参数7

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn8 | String | fields要加customizeGoodsColumn8 | 示例=货品自定义参数8

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn9 | String | fields要加customizeGoodsColumn9 | 示例=货品自定义字段9

- trades-tradeOrderGoodsColumnExts-customizeGoodsColumn10 | String | fields要加customizeGoodsColumn10 | 示例=货品自定义字段10

- trades-isDelete | Integer | 是否删除（0：否；1：是） | 示例=0

- trades-localPayment | BigDecimal | 应收合计（本币）fields要加localPayment | 示例=12.12

- trades-localExchangeRate | BigDecimal | 汇率（fields要加localExchangeRate） | 示例=12.12

- trades-customerAccount | String | 客户账号（入参字段加customerAccount） | 示例=12

- trades-localCurrencyCode | String | 公司本币（入参字段加上localCurrencyCode） | 示例=1

- trades-platCompleteTime | Date | 平台完成时间 入参fields要添加platCompleteTime | 示例=2021-11-26 00:00:00

- trades-buyerOpenUid | String | 21334 | 示例=平台买家唯一标识

- trades-qq | String | son串，内容包含：开票相关信息+buyerOpenUid | 示例=--

- trades-tradeOrderAssemblyGoodsDtoList | String | 组合装子件列表 | 示例=[]

- trades-tradeOrderAssemblyGoodsDtoList-shareFavourableAfterFee | String | 分摊后金额，分摊后金额=金额sellTotal-分摊金额shareFavourableFee | 示例=20

- trades-tradeOrderAssemblyGoodsDtoList-sellTotal | String | 金额 | 示例=20

- trades-tradeOrderAssemblyGoodsDtoList-sellPrice | String | 单价 | 示例=20

- trades-tradeOrderAssemblyGoodsDtoList-goodsNo | String | 货品编码 | 示例=luyx627234

- trades-tradeOrderAssemblyGoodsDtoList-unit | String | 单位 | 示例=个

- trades-tradeOrderAssemblyGoodsDtoList-specId | Integer | 规格id | 示例=12

- trades-tradeOrderAssemblyGoodsDtoList-goodsId | Integer | 货品id | 示例=734657

- trades-tradeOrderAssemblyGoodsDtoList-tradeId | BigDecimal | 销售单id | 示例=1739147106171755776

- trades-tradeOrderAssemblyGoodsDtoList-specName | String | 规格名称 | 示例=默认规格

- trades-tradeOrderAssemblyGoodsDtoList-goodsName | String | 货品名称 | 示例=货品名称

- trades-tradeOrderAssemblyGoodsDtoList-sellCount | BigDecimal | 销售数量 | 示例=12

- trades-tradeOrderAssemblyGoodsDtoList-subTradeId | BigDecimal | 子单号 | 示例=1739147735874964736

- trades-tradeOrderAssemblyGoodsDtoList-baseUnitSellCount | BigDecimal | 基础单位销售数量 | 示例=2

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery | Array | 组合装子件批次 | 示例=[]

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery-tradeId | String | 订单id | 示例=123

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery-specId | String | 规格id | 示例=123

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery-batchNo | String | 批次号 | 示例=DEFAULT

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery-expireDate | String | 过期事件 | 示例=0021-05-02 00:00:00

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery-subTradeId | String | 明细id | 示例=123

- trades-tradeOrderAssemblyGoodsDtoList-assemblyGoodsDelivery-productDate | String | 生成时间 | 示例=2021-11-26 00:00:00

- trades-tradeOrderRefundTime | String | 销售单退款时间 | 示例=2023-09-01 15:00:00

- trades-assemblyGoodsDetail | String | 组合装母件数据 | 示例=[]

- trades-apiType | Integer | 平台类型（渠道类型） | 示例=1196

- trades-logisticCode | String | 物流公司编码 | 示例=logisticCode

- trades-agentShopName | String | 分销商销售渠道 | 示例=agentShopName

- trades-tradeStatusExplain | String | 订单状态 | 示例=-

- trades-flagIds | String | 标价id | 示例=121312412312312312

- trades-flagNames | String | 标记名称 | 示例=冻结

- trades-sysFlagIds | String | 系统标记id | 示例=12311212313123123

- trades-shopTypeCode | String | 平台类型 | 示例=TMALL

- trades-sourceAfterNo | String | 售后来源单号 | 示例=JY02293293

- trades-ticketCodeList | Array | 卡券code列表 | 示例= ["32746523","23452546"]

- trades-allCompassSourceContentType | String | 抖音订单标记 | 示例= "直播间,短视频,其他"

- trades-customerName | String | 客户名称 | 示例=客户名称123

- trades-invoiceAmount | BigDecimal | 可开票金额 | 示例=0

- trades-realFee | BigDecimal | 实付金额 | 示例=0

- trades-packageDetail | Array | 包裹详情 | 示例=[]

- trades-packageDetail-isGift | Integer | 系统赠品标记 | 示例=0

- trades-packageDetail-barcode | String | 货品条码 | 示例=123456

- trades-packageDetail-tradeNo | String | 订单编号 | 示例=JY201906050001

- trades-packageDetail-buyerMemo | String | 客户备注 | 示例=客户备注

- trades-packageDetail-sellCount | BigDecimal | 货品数量 | 示例=10

- trades-packageDetail-isPlatGift | String | 平台赠品标记 | 示例=0

- trades-packageDetail-logisticNo | String | 物流单号 | 示例=LP3618168

- trades-packageDetail-sellerMemo | String | 客服备注 | 示例=客服备注

- trades-packageDetail-consignTime | String | 发货时间 | 示例=2024-04-09 11:27:25

- trades-packageDetail-logisticCode | String | 物流公司编号 | 示例=物流公司编号

- trades-packageDetail-logisticName | String | 物流公司 | 示例=物流公司

- trades-packageDetail-sourceTradeNo | String | 网店订单号 | 示例=123456

- trades-packageDetail-warehouseName | String | 发货仓库 | 示例=发货仓库

- trades-packageDetail-sourceSubtradeNo | String | 网店子订单号 | 示例=123456

- trades-finReceiptTime | Date | 收款日期 | 示例=2024-04-09 11:27:25

- trades-extraLogisticNo | String | 额外物流单号,多个用逗号分割 | 示例=78787,345345

- trades-warehouseId | String | 仓库id | 示例=123

- trades-govSubsidy | String | 政府补贴 | 示例=-

- trades-receiptAmount | BigDecimal | 收款金额 | 示例=0

- trades-pickUpTime | String | 揽件时间 | 示例=pickUpTime

- trades-platConsignTime | Date | 平台发货时间 | 示例=2026-01-20 19:40:00

- trades-platFlags | String | platFlags | 示例=国补,SOP

- trades-email | String | 邮箱 | 示例=1234@163.com

- trades-tradeOrderPre | Object | 预售信息 | 示例={“frstPaytime”:"2024-01-01 00:00:00","firstPayment":2.0}

- trades-tradeOrderPre-frstPaytime | Date | 付首款时间 | 示例=2024-01-01 00:00:00

- trades-tradeOrderPre-firstPayment | BigDecimal | 付首款金额 | 示例=20

- trades-tradeOrderPre-finalPaytime | Date | 付尾款时间 | 示例=2024-01-01 00:00:00

- trades-tradeOrderPre-finalPayment | BigDecimal | 付尾款金额 | 示例=20

- trades-tradeOrderPre-preTypedetail | String | 预售类别描述 | 示例=preTypedetail

- scrollId | String | 游标id。用于下次请求入参 | 示例=e435cb66390bb1eac99aa5755805f9f7

### JSON请求示例

```json

{"startPlatCompleteTime":"2024-09-09 11:27:25","pageSize":5,"endConsignTime":"2024-10-19 11:26:00","startNotifyPickTime":"2025-12-01 00:00:00","endBillDate":"2025-12-16 23:59:59","startConsignTime":"2024-10-15 11:26:00","logisticIdList":"[388942822334274688,1518158299225922688,1611460754588861952]","logisticId":"1068646551979302016","warehouseIds":"[\"1718178122057024640\",\"1718178122057024640\"]","endSigningTime":"2024-06-11 11:26:00","startCompleteTime":"2025-12-01 00:00:00","currentMaxId":"123456789","tradeNo":"JY202406050002","tradeTypeList":"[1,2]","mainPostId":"","startSettleTime":"2025-12-01 00:00:00","startFinReceiptTime":"2025-12-01 00:00:00","startModified":"2024-06-05 11:26:00","startConfirmTime":"2025-12-01 00:00:00","isBillCheck":1,"tradeTime":"2025-12-01 10:30:00","isReturnPddData":1,"mainPostIdList":"","tradeStatus":9090,"fields":"tradeNo,orderNo,shopName,companyName,warehouseName,logisticName,mainPostid,goodsDetail.goodsNo,flagNames,columnExt,sourceAfterNo,goodsDetail.outerId,pickUpCode,expense.expenseFee,expense.expenseItemName,billDate,goodsPlatDiscountFee,goodsDetail.shareOrderDiscountFee,goodsDetail.shareOrderPlatDiscountFee,customizeGoodsColumn9,goodsDetail.goodsId,goodsDetail.sellCount,goodsDetail.needProcessCount,goodsDetail.baseUnitSellCount,goodsDetail.assessmentCost,goodsDetail.compassSourceContentTypem,sourceTradeNo,shopId,warehouseId,scrollId","tradeStatusList":"[1010, 1050, 6000]","startBillDate":"2025-12-01 00:00:00","endCompleteTime":"2025-12-16 23:59:59","isTableSwitch":1,"endNotifyPickTime":"2025-12-16 23:59:59","startTradeTime":"2025-12-01 00:00:00","scrollId":"e435cb66390bb1eac99aa5755805f9f7","endCreated":"2024-06-11 11:26:00","endAuditTime":"2024-06-11 11:26:00","shopIds":"[\"1647727244400592896\",\"1647727244400592886\"]","startAuditTime":"2024-06-05 11:26:00","endPlatCompleteTime":"2024-09-15 11:27:25","tradeDeliveryNo":"“JY202512160001,JY202512160002”","tradeType":1,"isDelete":"0","customerTradeNos":"“1002663531489534600,1002663531489534601”","startSigningTime":"2024-06-05 11:26:00","endModified":"2024-06-11 11:26:00","endFinReceiptTime":"2025-12-16 23:59:59","endTradeTime":"2025-12-16 23:59:59","startCreated":"2024-06-05 11:26:00","endConfirmTime":"2025-12-16 23:59:59","tradeIds":"[2307317872088616192,2325498819791326465]","sourceTradeNos":"D241015171823K00002Z01","isPddQuery":1,"endSettleTime":"2025-12-16 23:59:59"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"scrollId":"e435cb66390bb1eac99aa5755805f9f7","trades":[{"customerDiscountFee":10,"buyerOpenUid":"平台买家唯一标识","state":"","departName":"","qq":"--","chargeExchangeRate":0.7868,"flagIds":"121312412312312312","tradeNo":"","customerPostFee":1,"assemblyGoodsDetail":"[]","completeTime":"2020-01-01 00:00:00","invoiceCode":"","customerName":"客户名称123","estimateWeight":1000,"isBillCheck":1,"tradeCount":4,"auditTime":"2019-06-05 11:26:00","chargeCurrency":"人民币","customerAccount":"12","apiType":1196,"buyerMemo":"","couponFee":0,"gmtModified":"2019-06-05 11:26:00","warehouseName":"","allCompassSourceContentType":" \"直播间,短视频,其他\"","platCompleteTime":"2021-11-26 00:00:00","receiptAmount":0,"blackList":0,"payerName":"","taxFee":0,"sysFlagIds":"12311212313123123","shopTypeCode":"TMALL","tradeType":0,"email":"1234@163.com","specialReminding":"","tradeStatusExplain":"-","otherFee":0,"customerGradeName":"","auditor":"","postFee":0,"pickUpTime":"pickUpTime","abnormalDescription":"","payerPhone":"","reviewer":"","signingTime":"2022-01-07 15:30:46","finalPaytime":"2019-06-05 11:26:00","register":"","seller":"","country":"","discountFee":10,"payTime":"2019-06-05 11:26:00","mainPostid":"1000111","flagNames":"冻结","invoiceAmount":0,"extraLogisticNo":"78787,345345","payerRegno":"","shopcode":"-","customerDiscount":1,"invoiceType":0,"shopId":"123","logisticCode":"logisticCode","town":"","billDate":"2019-06-05 11:26:00","estimateVolume":0,"tradeTime":"2019-06-05 11:26:00","platFlags":"国补,SOP","district":"","goodsSerial":[{"serialNo2":"123456","batchNo":"1234","subTradeId":"123123123","skuId":"123123","serialNo":"123213"}],"customerTags":"","reviewTime":"2019-06-05 11:26:00","firstPaytime":"2019-06-05 11:26:00","cityCode":"","tradeOrderAssemblyGoodsDtoList":{"assemblyGoodsDelivery":[{"productDate":"2021-11-26 00:00:00","specId":"123","batchNo":"DEFAULT","subTradeId":"123","expireDate":"0021-05-02 00:00:00","tradeId":"123"}],"goodsName":"货品名称","shareFavourableAfterFee":"20","specName":"默认规格","specId":12,"subTradeId":1739147735874964736,"sellCount":12,"goodsId":734657,"sellPrice":"20","unit":"个","sellTotal":"20","goodsNo":"luyx627234","baseUnitSellCount":2,"tradeId":1739147106171755776},"packageDetail":[{"tradeNo":"JY201906050001","isPlatGift":"0","buyerMemo":"客户备注","warehouseName":"发货仓库","sourceSubtradeNo":"123456","barcode":"123456","logisticCode":"物流公司编号","isGift":0,"sellCount":10,"consignTime":"2024-04-09 11:27:25","sourceTradeNo":"123456","sellerMemo":"客服备注","logisticNo":"LP3618168","logisticName":"物流公司"}],"isTableSwitch":1,"ticketCodeList":" [\"32746523\",\"23452546\"]","stockoutNo":"CK201906050001","warehouseCode":"","payNo":"201906000000000000000","finalPayment":0,"activationTime":"2019-06-05 11:26:00","onlineTradeNo":"","receivedTotal":190,"agentShopName":"agentShopName","totalFee":200,"packageWeight":1050,"companyName":"","finReceiptTime":"2024-04-09 11:27:25","appendMemo":"","payType":1,"payment":190,"customerTotalFee":10,"zip":"","confirmTime":"2019-06-05 11:26:00","warehouseId":"123","tradeStatus":1010,"notifyPickTime":"2019-06-05 11:26:00","logisticType":1,"city":"","customerCode":"","payerBankAccount":"","firstPayment":0,"countryCode":"","sourceAfterNo":"JY02293293","grossProfit":100,"realFee":0,"checkTotal":0,"payerBankName":"","localCurrencyCode":"1","gmtCreate":"2019-06-05 11:26:00","chargeCurrencyCode":"CNY","tradeOrderColumnExt":{"customizeTradeColumn2":"","customizeTradeColumn1":"","customizeTradeColumn6":"","customizeTradeColumn5":"","customizeTradeColumn4":"","customizeTradeColumn3":"","customizeTradeColumn9":"","customizeTradeColumn8":"","customizeTradeColumn7":"","customizeTradeColumn10":"","customizeTradeColumn23":"","tradeId":"123"},"lastShipTime":"2019-06-05 11:26:00","goodsTypeCount":2,"tradeOrderRefundTime":"2023-09-01 15:00:00","otherPaymentFees":[{"expenseItemName":"-","expenseFee":12}],"consignTime":"2019-06-05 11:26:00","invoiceNo":"","platConsignTime":"2026-01-20 19:40:00","orderNo":"","localExchangeRate":12.12,"sellerMemo":"","accountName":"支付宝账号","tradeOrderPre":{"finalPaytime":"2024-01-01 00:00:00","frstPaytime":"2024-01-01 00:00:00","finalPayment":20,"firstPayment":20,"preTypedetail":"preTypedetail"},"shopName":"","tradeOrderGoodsColumnExts":[{"customizeGoodsColumn10":"货品自定义字段10","subTradeId":"123","customizeGoodsColumn5":"货品自定义参数5","customizeGoodsColumn6":"货品自定义参数6","customizeGoodsColumn7":"货品自定义参数7","customizeGoodsColumn8":"货品自定义参数8","customizeGoodsColumn1":"货品自定义字段1","customizeGoodsColumn2":"货品自定义参数2","customizeGoodsColumn3":"货品自定义参数3","customizeGoodsColumn4":"货品自定义参数4","customizeGoodsColumn9":"货品自定义字段9","tradeId":"132"}],"freezeReason":"","preTypedetail":"","customerPayment":12,"govSubsidy":"-","localPayment":12.12,"goodslist":"","receivedPostFee":12,"isDelete":0,"customerTypeName":"","payerAddress":"","logisticName":"","tradeFrom":1,"tradeOrderPayList":[{"chargeExchangeRate":12,"chargeCurrency":"","chargeAccount":"","chargeType":1,"payNo":"","payType":1,"payme

```

## oms.order.confirm.delivery（发货确认）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-12-10 15:52:50.0

说明：有外部发货标记的销售单，或者平台发货的销售单，当网店订单交易状态为等买家收货或交易成功，销售单更新为发货在途

常见问题：

请求字段数：3；返回字段数：4

### 请求字段

- deliveryDtoList | Array | 必填=True | 订单发货信息列表 | 示例=-

- deliveryDtoList-tradeNo | String | 必填=True | 销售订单号 | 示例=JY202101041136

- deliveryDtoList-tradeStatus | String | 必填=True | 订单状态: 等待买家确认收货,即:卖家已发货:WAIT_BUYER_CONFIRM_GOODS; 交易成功: TRADE_FINISHED | 示例=WAIT_BUYER_CONFIRM_GOODS

### 返回字段

- isSuccess | Boolean | 是否成功，全部成功才为成功，即failedResults数组为空时未true | 示例=TRUE

- failedResults | Array | 取消订单处理失败结果 | 示例=-

- failedResults-tradeNo | String | 销售订单号 | 示例=101999000000

- failedResults-msg | String | 订单处理失败消息 | 示例=未找到销售订单信息

### JSON请求示例

```json

{"deliveryDtoList":[{"tradeNo":"JY202101041136","tradeStatus":"WAIT_BUYER_CONFIRM_GOODS"}]}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"isSuccess":true,"failedResults":[{"tradeNo":"101999000000","msg":"未找到销售订单信息"}]},"contextId":"1970477664243646848"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"1970477664243646848"},"subCode":"0130020001"}

```

## wms.order.query-info（查询发货单）

接口等级：标准接口; bSubscription：True; bAuthorized：True; postType：1; 最近发布时间：2025-08-21 11:13:27.0

说明：此接口不包含淘系和拼多多的数据，其它平台的敏感信息会根据平台规则同步调整

常见问题：

请求字段数：3；返回字段数：42

### 请求字段

- orderNo | String | 必填=False | 发货单号(发货单号或者关联单号两者必填其一) | 示例=FH2008240002

- erpOrderNo | String | 必填=False | 关联单号(发货单号或者关联单号两者必填其一) | 示例=FH2008240002

- logisticNo | String | 必填=False | 物流单号(有物流单号可以不传关联单号或者发货单号) | 示例=SF13221139913

### 返回字段

- orderNo | String | 发货单号 | 示例=FH2008240002

- ownerName | String | 货主名称 | 示例=自营

- warehouseName | String | 仓库名称 | 示例=本地仓

- erporderNo | String | 关联销售单号 | 示例=JY123456420

- logisticNo | String | 物流编号 | 示例=SF753804870213

- logisticName | String | 物流公司名称 | 示例=顺丰

- logisticTypeName | String | logisticTypeName | 示例=普通快递

- orderStatusName | String | 发货单状态名称 | 示例=0 待作业 1待配货 3待验货 4待打包 5待称重 6待分拨 7已完成 8已取消

- sendTime | Date | 发货时间 | 示例=2020-08-21 16:41:25

- waveNo | String | 波次号 | 示例=W202008240001

- goodsDetail | Array | 货品明细 | 示例=

- goodsDetail-goodsNo | String | 货品编号 | 示例=

- goodsDetail-goodsName | String | 货品名称 | 示例=

- goodsDetail-skuBarcode | String | 规格条码 | 示例=

- goodsDetail-outSkuCode | String | 外部货品编码 | 示例=

- goodsDetail-skuName | String | 规格名 | 示例=

- goodsDetail-sellCount | BigDecimal | 数量 | 示例=10

- goodsDetail-sellPrice | BigDecimal | 单价 | 示例=10

- goodsDetail-sellTotal | BigDecimal | 总金额 | 示例=100

- goodsDetail-isGift | Integer | 赠品标记 | 示例=0

- goodsDetail-detailId | Long | 明细唯一ID | 示例=413606730978302848

- goodsDetail-remark | String | 备注 | 示例=备注参考

- goodsDetail-snList | Array | 唯一码 | 示例=sn001

- goodsDetail-sn2List | Array | 唯一码2 | 示例=sn002

- receiverName | String | 收件人 | 示例=张三

- customerCode | String | 客户编码 | 示例=112233

- customerName | String | 客户名称 | 示例=一二三四五六七八九十

- estimateWeight | BigDecimal | 发货单预估重量 | 示例=100

- orderFee | BigDecimal | 操作费用 | 示例=20

- shopName | String | 销售渠道 | 示例=测试111

- picker | String | 配货员 | 示例=张三

- checkTime | String | 验货时间 | 示例=2024-10-15 11:25:36

- finishTime | String | 完成时间 | 示例=2024-10-15 11:25:36

- checker | String | 验货人 | 示例=user1

- weigher | String | 称重人 | 示例=user1

- weighTime | String | 称重时间 | 示例=2020-08-21 16:41:25

- packer | String | 打包人 | 示例=user1

- packTime | String | 打包时间 | 示例=2020-08-21 16:41:25

- allocator | String | 分拣人 | 示例=user1

- allocateTime | String | 分拣时间 | 示例=2020-08-21 16:42:25

- dispatcher | String | 分拨人 | 示例=user1

- dispatcherTime | String | 分拨时间 | 示例=2020-08-21 16:42:25

### JSON请求示例

```json

{"erpOrderNo":"FH2008240002","logisticNo":"SF13221139913","orderNo":"FH2008240002"}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"logisticNo":"SF753804870213","waveNo":"W202008240001","customerCode":"112233","orderFee":20,"shopName":"测试111","warehouseName":"本地仓","orderStatusName":"0 待作业 1待配货 3待验货 4待打包 5待称重 6待分拨 7已完成 8已取消","ownerName":"自营","logisticTypeName":"普通快递","picker":"张三","orderNo":"FH2008240002","receiverName":"张三","customerName":"一二三四五六七八九十","erporderNo":"JY123456420","sendTime":"2020-08-21 16:41:25","estimateWeight":100,"logisticName":"顺丰","goodsDetail":[{"sellTotal":100,"detailId":"413606730978302848","sellPrice":10,"remark":"备注参考","outSkuCode":"","skuName":"","tradeName":"","isGift":0,"goodsName":"","tradeSpec":"","tradeGoodsno":"","goodsNo":"","sn2List":"sn002","snList":"sn001","sellCount":10,"skuBarcode":""}]},"contextId":"2220266937660213120"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2220266937660213120"},"subCode":"0130020001"}

```

## wms.order.query-info.page（查询发货单（分页））

接口等级：标准接口; bSubscription：True; bAuthorized：False; postType：1; 最近发布时间：2026-04-22 11:33:03.0

说明：*此接口不包含淘系和拼多多的数据，其它平台的敏感信息会根据平台规则同步调整。

常见问题：

请求字段数：16；返回字段数：77

### 请求字段

- startFinishTime | String | 必填=True | 完成时间（起始） | 示例=2020-11-21 00:00:00

- endFinishTime | String | 必填=True | 完成时间（截止） | 示例=2020-11-21 23:59:59

- orderStatusList | Array | 必填=False | 发货单状态（0：待作业；1：待配货；3待验货；4：待打包；5：待称重；6：待分拨；7：已完成；8：已取消；15：待出库） | 示例=[0,1,7]

- pageSize | Integer | 必填=False | 每页记录数，默认50，最大200 | 示例=50

- pageIndex | Integer | 必填=False | 页码，0为第1页 | 示例=0

- orderNo | String | 必填=False | 发货单号（多个逗号分隔） | 示例=S2022040101,S2022040102

- ownerCode | String | 必填=False | 货主吉客号 支持查单个货主 | 示例="666666"

- isNeedCustomFields | Integer | 必填=False | 是否需要返回发货单和发货单明细自定义字段 1是 0否 | 示例=0

- outTypeList | Array | 必填=False | 出库类型（200：换货出库； 201：销售出库；202：调拨出库；203：盘亏出库；204：其他出库；205：采购退货；206：生产领料；207：组装拆卸出库；208：翻新出库；209：报废出库；210：残次品出库；211：倒冲领料；212：包材出库；215：维修还厂；216：次产出库；217：借用出库；218：归还出库；219：生产委外领料；220：换货出库；221：补发出库；222：调拨退货出库；223：生产余料出库；231：成本调价出库；299：可用库存修正） | 示例=["201"]

- relNo | String | 必填=False | 关联单号（多个逗号分隔） | 示例=JY2022040101,JY2022040102

- startModifyTime | String | 必填=False | 修改时间（起始） | 示例=2020-11-21 00:00:00

- endModifyTime | String | 必填=False | 修改时间（截止） | 示例=2020-11-21 23:59:59

- logisticNo | String | 必填=False | 物流单号（多个逗号分隔） | 示例=1000293,1000270

- startGmtCreate | String | 必填=False | 创建时间（起始） | 示例=2020-11-21 00:00:00

- endGmtCreate | String | 必填=False | 创建时间（截止） | 示例=2020-11-21 23:59:59

- isNeedSnInfo | Integer | 必填=False | 是否返回唯一码信息：0否1是 | 示例=1

### 返回字段

- orderNo | String | 发货单号 | 示例=FH2008240002

- ownerName | String | 货主名称 | 示例=自营

- warehouseName | String | 仓库名称 | 示例=本地仓

- erporderNo | String | 关联销售单号 | 示例=JY123456420

- logisticNo | String | 物流编号 | 示例=SF753804870213

- logisticName | String | 物流公司名称 | 示例=顺丰

- logisticTypeName | String | 物流类型名称 | 示例=普通快递

- orderStatusName | String | 发货单状态名称 | 示例=0 待作业 1待配货 3待验货 4待打包 5待称重 6待分拨 7已完成 8已取消

- sendTime | Date | 发货时间 | 示例=2020-08-21 16:41:25

- waveNo | String | 波次号 | 示例=W202008240001

- goodsDetail | Array | 货品明细 | 示例=

- goodsDetail-goodsNo | String | 货品编号 | 示例=

- goodsDetail-goodsName | String | 货品名称 | 示例=

- goodsDetail-skuBarcode | String | 规格条码 | 示例=

- goodsDetail-outSkuCode | String | 外部货品编码 | 示例=

- goodsDetail-skuName | String | 规格名 | 示例=

- goodsDetail-sellCount | BigDecimal | 数量 | 示例=10

- goodsDetail-sellPrice | BigDecimal | 单价 | 示例=10

- goodsDetail-sellTotal | BigDecimal | 总金额 | 示例=100

- goodsDetail-isGift | Integer | 赠品标记 | 示例=0

- goodsDetail-detailId | Long | 明细唯一ID | 示例=413606730978302848

- goodsDetail-unit | String | 单位 | 示例=瓶

- goodsDetail-skuId | Long | 货品规格id | 示例=123606730978305684

- goodsDetail-cateName | String | 货品分类 | 示例=日用品

- goodsDetail-actualCount | BigDecimal | 实发数量 | 示例=10

- goodsDetail-detailCustomField | Object | 发货单明细自定义字段 | 示例=发货单明细自定义字段

- goodsDetail-detailCustomField-customField1 | String | 自定义字段1 | 示例=明细1

- goodsDetail-detailCustomField-customField2 | String | 自定义字段2 | 示例=明细2

- goodsDetail-detailCustomField-customField3 | String | 自定义字段3 | 示例=自定义字段3

- goodsDetail-detailCustomField-customField4 | String | 自定义字段4 | 示例=自定义字段4

- goodsDetail-detailCustomField-customField5 | String | 自定义字段5 | 示例=自定义字段5

- goodsDetail-detailCustomField-customField6 | String | 自定义字段6 | 示例=自定义字段6

- goodsDetail-detailCustomField-customField7 | String | 自定义字段7 | 示例=自定义字段7

- goodsDetail-detailCustomField-customField8 | String | 自定义字段8 | 示例=自定义字段8

- goodsDetail-detailCustomField-customField9 | String | 自定义字段9 | 示例=自定义字段9

- goodsDetail-detailCustomField-customField10 | String | 自定义字段10 | 示例=自定义字段10

- goodsDetail-outDetailId | String | 外部明细id | 示例=1547525

- goodsDetail-snList | String | 唯一码信息 | 示例=-

- goodsDetail-sn2List | String | 唯一码2信息 | 示例=-

- ownerCode | String | 货主CODE | 示例=666666

- chargeCurrency | String | 币种 | 示例=人民币

- otherLogisticNo | String | 额外物流单号 | 示例=SF12345678,SF2222222

- flagNames | String | 发货单标记 | 示例=测试，标记

- platOrderNo | String | 原始单号 | 示例=DB202309210000016

- actualPayment | BigDecimal | 实付金额 | 示例=88

- orderCustomField | Object | 发货单自定义字段 | 示例=自定义字段

- orderCustomField-customField1 | String | 自定义字段1 | 示例=自定义字段1

- orderCustomField-customField2 | String | 自定义字段2 | 示例=自定义字段2

- orderCustomField-customField3 | String | 自定义字段3 | 示例=自定义字段3

- orderCustomField-customField4 | String | 自定义字段4 | 示例=自定义字段4

- orderCustomField-customField5 | String | 自定义字段5 | 示例=自定义字段5

- orderCustomField-customField6 | String | 自定义字段6 | 示例=自定义字段6

- orderCustomField-customField7 | String | 自定义字段7 | 示例=自定义字段7

- orderCustomField-customField8 | String | 自定义字段8 | 示例=自定义字段8

- orderCustomField-customField9 | String | 自定义字段9 | 示例=自定义字段9

- orderCustomField-customField10 | String | 自定义字段10 | 示例=自定义字段10

- orderTypeName | String | 出库类型 | 示例=销售出库

- tradeFromName | String | 订单来源 | 示例=手工新建

- orderTime | Date | 下单时间 | 示例=2024-03-18 00:00:00

- tradeConfirmTime | Date | 订单确认时间 | 示例=2024-03-18 00:00:00

- warehouseProcessTime | String | 仓库处理时间 | 示例=1分20秒

- orderProcessTime | String | 订单处理时间 | 示例=1分20秒

- actualPostage | String | 实际邮资 | 示例=22

- orderFileList | Array | 发货单附件 | 示例=[]

- orderFileList-fileName | String | 文件名称 | 示例=wms

- orderFileList-fileUrl | String | URL地址链接 | 示例=https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/wms/444648626932423808/2063164967749716352.jrpk?Expires=4882748436&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=kpc1PxbnT334grg1JO%2Fnsm100B8%3D

- logisticFee | BigDecimal | 物流费用 | 示例=0

- printTime | Date | 打单时间 | 示例=2024-10-15 11:25:36

- sellerMemo | String | 客服备注 | 示例=客服备注

- appendMemos | String | 追加备注 | 示例=追加备注

- buyerMemo | String | 客户备注 | 示例=客户备注

- shopName | String | 销售渠道 | 示例=测试111

- picker | String | 配货人 | 示例=张三

- signTime | Date | 签收时间 | 示例=2024-10-15 11:25:36

- packageWeight | BigDecimal | 包裹重量 | 示例=100

- checkTime | Date | 验货时间 | 示例=2024-10-15 00:00:00

- packAmount | Integer | 包裹数量 | 示例=2

### JSON请求示例

```json

{"endModifyTime":"2020-11-21 23:59:59","logisticNo":"1000293,1000270","orderNo":"S2022040101,S2022040102","startFinishTime":"2020-11-21 00:00:00","isNeedCustomFields":0,"ownerCode":"\"666666\"","outTypeList":"[\"201\"]","orderStatusList":"[0,1,7]","pageSize":50,"endFinishTime":"2020-11-21 23:59:59","relNo":"JY2022040101,JY2022040102","endGmtCreate":"2020-11-21 23:59:59","startGmtCreate":"2020-11-21 00:00:00","startModifyTime":"2020-11-21 00:00:00","pageIndex":0,"isNeedSnInfo":1}

```

### JSON返回示例

```json

{"code":200,"msg":"","result":{"data":{"waveNo":"W202008240001","packageWeight":100,"flagNames":"测试，标记","logisticFee":0,"orderStatusName":"0 待作业 1待配货 3待验货 4待打包 5待称重 6待分拨 7已完成 8已取消","orderTime":"2024-03-18 00:00:00","orderFileList":[{"fileName":"wms","fileUrl":"https://jkyun.oss-cn-hangzhou.aliyuncs.com/longterm/45/system/wms/444648626932423808/2063164967749716352.jrpk?Expires=4882748436&OSSAccessKeyId=LTAI5tPkb173kAgKZCTXcZWt&Signature=kpc1PxbnT334grg1JO%2Fnsm100B8%3D"}],"picker":"张三","tradeFromName":"手工新建","orderNo":"FH2008240002","signTime":"2024-10-15 11:25:36","tradeConfirmTime":"2024-03-18 00:00:00","orderCustomField":{"customField5":"自定义字段5","customField6":"自定义字段6","customField7":"自定义字段7","customField8":"自定义字段8","customField1":"自定义字段1","customField2":"自定义字段2","customField3":"自定义字段3","customField4":"自定义字段4","customField9":"自定义字段9","customField10":"自定义字段10"},"sendTime":"2020-08-21 16:41:25","actualPostage":"22","checkTime":"2024-10-15 00:00:00","sellerMemo":"客服备注","chargeCurrency":"人民币","buyerMemo":"客户备注","logisticNo":"SF753804870213","ownerCode":"666666","platOrderNo":"DB202309210000016","shopName":"测试111","warehouseName":"本地仓","orderProcessTime":"1分20秒","actualPayment":88,"ownerName":"自营","logisticTypeName":"普通快递","otherLogisticNo":"SF12345678,SF2222222","warehouseProcessTime":"1分20秒","erporderNo":"JY123456420","orderTypeName":"销售出库","appendMemos":"追加备注","logisticName":"顺丰","goodsDetail":[{"detailId":"413606730978302848","sellPrice":10,"cateName":"日用品","outSkuCode":"","goodsName":"","skuId":"123606730978305684","unit":"瓶","sellCount":10,"sellTotal":100,"actualCount":10,"skuName":"","isGift":0,"goodsNo":"","detailCustomField":{"customField5":"自定义字段5","customField6":"自定义字段6","customField7":"自定义字段7","customField8":"自定义字段8","customField1":"明细1","customField2":"明细2","customField3":"自定义字段3","customField4":"自定义字段4","customField9":"自定义字段9","customField10":"自定义字段10"},"outDetailId":"1547525","sn2List":"-","snList":"-","skuBarcode":""}],"printTime":"2024-10-15 11:25:36"},"contextId":"2376343924312736512"},"subCode":""}*@*{"code":0,"msg":"未知错误","result":{"data":null,"contextId":"2376343924312736512"},"subCode":"0130020001"}

```