# demo_multiply.py
from .mpc_core.shamir import shamir_split, shamir_reconstruct
from .mpc_core.beaver import beaver_triple, mpc_multiply

x, y = 5, 7
triple = beaver_triple()
x_shares = shamir_split(x)
y_shares = shamir_split(y)

z_shares = mpc_multiply(x_shares, y_shares, triple)
product = shamir_reconstruct(z_shares)

print("Final Product:", product)
