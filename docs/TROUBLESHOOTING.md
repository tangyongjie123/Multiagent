# 常见故障与修复记录

更新时间：2026-11-02

## 图书管理系统连续超时

### 现象

- Coder Agent 连续返回 `OpenAITimeoutError`。
- 修复次数达到上限后运行失败。
- 工作区只有 `pom.xml`、PM 和 Architect 结果，没有业务代码。

### 根因

早期 Coder 在单次模型调用中生成全部业务代码。代码规模较大时，模型接口可能在输出完成前超时。

### 修复

- Coder 改为两阶段生成：
  1. Entity、DTO、Repository 和 Service。
  2. Controller、异常处理、Web 配置。
- 第二阶段读取第一阶段真实生成的 Service 和 DTO 源码，禁止自行猜测方法名。
- 生成项目改用 Architect 输出的动态包名，图书系统使用 `com.example.book`。

## 运行被误标为中断

### 现象

- 运行仍在模型调用或 Maven 测试，却出现 `run.interrupted`。
- 同一 PostgreSQL 数据库同时连接多个后端实例时容易发生。

### 根因

早期启动恢复逻辑会把所有 `running` 运行直接标记为中断，无法区分运行是否由另一个存活进程持有。

### 修复

- Run 增加 `worker_id` 和 `heartbeat_at`。
- 运行执行期间每 15 秒更新心跳。
- 启动恢复只处理心跳超过 60 秒且开始时间同样超时的运行。

## Maven 编译错误

### 常见原因

- Controller 调用不存在的 Service 方法。
- 使用未声明依赖的注解。
- OpenAPI 注解属性与依赖版本不兼容。

### 修复

- Web 层生成必须读取真实 Service/DTO 源码。
- 模板 POM 已包含 Springdoc OpenAPI。
- Reviewer 不通过时回到 Coder，随后重新执行真实 Maven 测试。

## 测试覆盖不足

### 修复

Tester 现在生成完整 REST 契约测试：

- 应用上下文启动。
- 列表查询。
- 创建成功。
- 按 ID 查询。
- 修改。
- 删除后返回 404。
- 空请求体返回 400。
- 重复 ISBN 返回 409。

## 重新运行

旧失败运行不能直接恢复，应启动新的运行：

1. 停止现有后端和前端。
2. 在项目根目录运行 `python dev.py`。
3. 在页面选中“图书管理系统”。
4. 点击“启动新运行”。
5. 不要重复点击，等待状态变为 `completed` 或明确失败。
