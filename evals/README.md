# AI/RAG 离线评测

该评测集验证不依赖模型供应商的安全底线：审核资料召回、未审核资料隔离、证据不足拒答、风险识别、长对话摘要保真和联系方式脱敏。

```powershell
$env:PYTHONPATH='.'
python evals/run_evals.py
```

结果写入 `evals/results/latest.json`。CI 会执行相同命令，并根据 `cases.json` 中的质量门槛失败或通过。

这不是医疗有效性证明，也不评价真实大模型的共情质量。真实模型上线前仍需经过受控人工评审、红队测试和专业人员审核。
