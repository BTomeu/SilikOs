/* what a firmware often carries: when it was built. __DATE__ and __TIME__ are the compiler's clock, unless
 * SOURCE_DATE_EPOCH is set: then they are that instant (GCC 7 and later), and two builds give the same bytes. */
const char build_info[] __attribute__((used)) = "built " __DATE__ " " __TIME__;
