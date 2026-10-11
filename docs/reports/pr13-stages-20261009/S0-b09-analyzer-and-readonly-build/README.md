# B09 编译检查与只读构建

第二轮保持源文件、依赖原字节不变，编译只报 xUnit2031。将先 Where 再 Assert.Single 改为 Assert.Single 的筛选函数重载，保留相同唯一实例条件。云端实际 SDK 的 build/test 帮助已确认支持 --artifacts-path；第三轮源目录整体只读，构建输出写入独立受限目录。

两个失败 attempt 的源目录、日志和输出继续保留。本阶段是修复交付，第三轮编译及 Godot/C# 完整协议链仍待实际验证，没有授予通过。
