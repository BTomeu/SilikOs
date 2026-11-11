// silik dev try: C++ for the same processor, without exceptions or run-time type information.
#include <array>
#include <cstdint>

template <typename T, std::size_t N>
constexpr T sum(const std::array<T, N> &a) {
    T s{};
    for (auto v : a) s += v;
    return s;
}

static constexpr std::array<std::uint32_t, 4> values{1, 2, 3, 4};
static_assert(sum(values) == 10, "computed by the compiler");

volatile std::uint32_t result;

int main() {
    result = sum(values);
    for (;;) { }
}
