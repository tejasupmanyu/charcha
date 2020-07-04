var tribute = new Tribute({
        values: getUsers,
});

function getUsers(text, cb) {
  $.get("/api/users/search?q="+text)
  .done(function(data){
    cb(transformUsers(data))
  })
  .fail(function(data){
    console.error(data)
    cb([])
  });
}

function transformUsers(users) {
  const result = []
  for(var user of users) {
    result.push({"key": user.username, value: user.id})
  }
  return result
}

function onMentionSelect(event) {
  // delete the matching text and the at sign
  match_size = (event.detail.item.string.match(/<span>/g) || []).length
  var editor = $('trix-editor')[0].editor;
  for(var i=0; i<=match_size; i++) {
    editor.deleteInDirection("backward")
  }

  // add the mention as an attachment
  mention = event.detail.item.original
  attachment = new Trix.Attachment({
    user_id: mention.value,
    content: "<span class='mention' data-user-id=" + mention.value + ">@"+ mention.key + "</span>",
  })
  editor.insertAttachment(attachment)
  editor.insertString(" ") // add an empty space to continue
}

$(document).ready(function(){
  tribute.attach($('trix-editor'));
  $('trix-editor').on('tribute-replaced', onMentionSelect)
  tribute.range.pasteHtml = function(html, startPos, endPos) {}
});

