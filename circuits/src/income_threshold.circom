pragma circom 2.1.6;

include "circomlib/circuits/comparators.circom";

template IncomeThreshold() {
    signal input amount;
    signal input threshold;
    signal output ok;

    component cmp = GreaterEqThan(32); // 比较 32-bit 数字
    cmp.in[0] <== amount;
    cmp.in[1] <== threshold;
    ok <== cmp.out;
}

// 将 threshold 设为 public 输入，便于链上验证时公开
component main { public [ threshold ] } = IncomeThreshold();
