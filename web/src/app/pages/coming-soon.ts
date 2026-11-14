import { Component, input } from '@angular/core';

@Component({
  selector: 'app-coming-soon',
  template: `
    <h1>{{ heading() }}</h1>
    <div class="panel empty">
      <p>{{ text() }}</p>
      <p class="muted">Built in Phase {{ phase() }}.</p>
    </div>
  `,
})
export class ComingSoonPage {
  heading = input('');
  text = input('');
  phase = input(0);
}
