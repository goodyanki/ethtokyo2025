# demo_sum.py
from .mpc_core.shamir import shamir_split, shamir_reconstruct

# 三方输入
x, y, z = 5, 7, 9
x_shares = shamir_split(x)
y_shares = shamir_split(y)
z_shares = shamir_split(z)

# 各方持有自己的一份
party1 = [x_shares[0], y_shares[0], z_shares[0]]
party2 = [x_shares[1], y_shares[1], z_shares[1]]
party3 = [x_shares[2], y_shares[2], z_shares[2]]

# 本地部分和
local_sums = {
    1: sum(v for (_, v) in party1),
    2: sum(v for (_, v) in party2),
    3: sum(v for (_, v) in party3),
}

# 重建
collected = [(1, local_sums[1]), (2, local_sums[2]), (3, local_sums[3])]
total = shamir_reconstruct(collected)

print("Final Sum:", total)
