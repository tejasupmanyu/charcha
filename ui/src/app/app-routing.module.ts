import { NgModule } from '@angular/core';
import { Routes, RouterModule } from '@angular/router';
import { DiscussionDetailsComponent } from './discussion-details/discussion-details.component';
import { DiscussionsComponent } from './discussions/discussions.component';

const routes: Routes = [
  {path: '', component: DiscussionsComponent},
  {path: 'discuss/:id', component: DiscussionDetailsComponent}
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
