import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { DiscussionsComponent } from './discussions/discussions.component';
import { DiscussionDetailsComponent } from './discussion-details/discussion-details.component';

@NgModule({
  declarations: [
    AppComponent,
    DiscussionsComponent,
    DiscussionDetailsComponent
  ],
  imports: [
    BrowserModule,
    AppRoutingModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
