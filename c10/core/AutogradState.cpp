#include <c10/core/AutogradState.h>

namespace c10 {

namespace {
// By default, grad mode is enabled and inference mode is disabled
thread_local AutogradState autograd_state_tls =
    AutogradState(/* grad_mode */ true, /* inference_mode */ false);
} // namespace

AutogradState& AutogradState::get_tls_state() {
  return autograd_state_tls;
}

void AutogradState::set_tls_state(AutogradState state) {
  autograd_state_tls = state;
}

} // namespace c10
