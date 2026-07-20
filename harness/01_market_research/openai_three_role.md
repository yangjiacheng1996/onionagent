
# 我的提问
使用python的OpenAI库发送提示词时，是否需要标记我的提示词是系统提示词System Prompt还是用户提示词User Prompt？

# 调研结果




在使用Python的OpenAI库调用`chat.completions`接口时，**必须明确标记提示词的角色（如`system`、`user`或`assistant`）**，这是OpenAI API的强制要求，而非可选操作。若未正确区分角色，API可能返回错误或无法按预期生成结果。

---

## 一、为什么必须标记角色？
### 1. **API设计要求**
OpenAI的`chat.completions`接口**强制要求每条消息必须包含`role`字段**，用于定义消息的语义角色。角色类型包括：
- **`system`**：设定模型行为规则（如身份、能力边界）。
- **`user`**：用户输入的实际查询或指令。
- **`assistant`**：模型的历史回复（用于多轮对话上下文）。

若省略`role`或使用无效值，API会直接返回错误（如`InvalidRequestError`）。

### 2. **角色影响模型行为**
- **`system`提示词**：  
  用于**初始化模型的行为框架**（例如“你是一个Python专家”），对后续所有交互生效。  
  **关键作用**：约束输出风格、设定知识范围、避免越界回答。
- **`user`提示词**：  
  代表**当前用户的实际请求**（如“写一个快速排序函数”），是每次调用的核心输入。
- **`assistant`提示词**：  
  用于传递**模型之前的回复**，维持多轮对话的连贯性。

---

## 二、正确用法示例
### 1. **基础单次调用（含角色标记）**
```python
from openai import OpenAI

client = OpenAI(api_key="YOUR_API_KEY")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "你是一个Python编程专家，只输出代码和必要注释"},  # 系统指令
        {"role": "user", "content": "用Python实现快速排序，要求包含类型注解"}             # 用户请求
    ]
)
print(response.choices.message.content)
```

### 2. **多轮对话（需维护历史消息）**
```python
# 初始化对话历史（必须包含角色）
messages = [
    {"role": "system", "content": "你是一个客服助手，回答简洁不超过3句"},
    {"role": "user", "content": "订单无法支付怎么办？"},
    {"role": "assistant", "content": "请检查银行卡余额或联系银行确认支付限额。"}
]

# 新用户提问（追加到历史）
messages.append({"role": "user", "content": "需要提供身份证吗？"})

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=messages  # 传递完整历史
)
```

---

## 三、常见错误与注意事项
### 1. **错误用法**
- **省略`role`字段**：  
  ```python
  # 错误！API会报错
  messages = [{"content": "写一个Python函数"}]
  ```
- **混淆角色用途**：  
  将系统指令（如“用中文回答”）放在`user`角色中，可能导致模型忽略关键约束。

### 2. **关键建议**
- **`system`提示词应简洁明确**：  
  避免冗长描述，**优先指定身份、输出格式和约束条件**（例如“只输出JSON，不要解释”）。
- **多轮对话需完整传递历史**：  
  模型**无记忆能力**，必须将所有历史消息（含角色）一次性传入`messages`参数。
- **生产环境需控制长度**：  
  `messages`总长度（含输入/输出）**不能超过模型上下文限制**（如GPT-4o为128k tokens），过长需截断或摘要处理。

---

## 四、与旧版`completions`接口的区别
若使用已弃用的`completions.create`接口（如`text-davinci-003`），**无需角色标记**，但该接口仅支持单轮文本补全，**不适用于对话场景**。  
**当前主流实践应使用`chat.completions`并严格区分角色**，以确保交互逻辑清晰、结果可控。