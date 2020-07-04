function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

$('.upvote-button').click(function(){
    //the button that was clicked (upvote or downvote)
    var elem = $(this);
    var score = elem.find(".score");
    var objectType = elem.data("object-type");
    var objectId = elem.data("object-id");
    
    var url = "/api/" + objectType + "/" + objectId + "/upvote";
    
    var csrftoken = getCookie('csrftoken');
    $.post(url, {'csrfmiddlewaretoken': csrftoken })
        .done(function(data){
          score.html(data);
        })
        .fail(function(data){
          score.html('?');
        });
});


(function() {
    var uploadUrl = "/api/upload";
    
    addEventListener("trix-attachment-add", function(event) {
      if (event.attachment.file) {
        uploadFileAttachment(event.attachment)
      }
    })
  
    function uploadFileAttachment(attachment) {
      uploadFile(attachment.file, setProgress, setAttributes)
  
      function setProgress(progress) {
        attachment.setUploadProgress(progress)
      }
  
      function setAttributes(attributes) {
        attachment.setAttributes(attributes)
      }
    }
  
    function uploadFile(file, progressCallback, successCallback) {
      var key = createStorageKey(file)
      var formData = createFormData(key, file)
      var xhr = new XMLHttpRequest()
  
      xhr.open("POST", uploadUrl, true)
  
      xhr.upload.addEventListener("progress", function(event) {
        var progress = event.loaded / event.total * 100
        progressCallback(progress)
      })
  
      xhr.addEventListener("load", function(event) {
        if (xhr.status == 200) {
          var response = JSON.parse(xhr.responseText);
          
          var attributes = {
            url: response['fileUrl'],
            href: response['fileUrl']
          }
          console.log(attributes);
          successCallback(attributes)
        }
      })
  
      xhr.send(formData)
    }
  
    function createStorageKey(file) {
      var date = new Date()
      var day = date.toISOString().slice(0,10)
      var name = date.getTime() + "-" + file.name
      return [ "tmp", day, name ].join("/")
    }
  
    function createFormData(key, file) {
      var data = new FormData()
      data.append("csrfmiddlewaretoken", getCookie('csrftoken'));
      data.append("key", key)
      data.append("Content-Type", file.type)
      data.append("file", file)
      return data
    }
  })();

function setupMentions() {
  var tribute = new Tribute({
          values: [
              {key: 'Phil Heartman', value: 'pheartman'},
              {key: 'Gordon Ramsey', value: 'gramsey'}
          ],
  });
  tribute.attach($('trix-editor'));
  var editor = $('trix-editor')[0].editor;

  function replaced(event) {
    // delete the matching text and the at sign
    match_size = (event.detail.item.string.match(/<span>/g) || []).length + 1
    for(var i=0; i<=match_size; i++) {
      editor.deleteInDirection("backward")
    }

    // add the mention as an attachment
    mention = event.detail.item.original
    attachment = new Trix.Attachment({
      user_id: mention.value,
      content: "<span class='mention'>@"+ mention.value + "</span>",
    })
    editor.insertAttachment(attachment)
    editor.insertString(" ") // add an empty space to continue
  }

  $('trix-editor').on('tribute-replaced', replaced)
}

  /* Disable submit button once clicked to prevent accidental double submission */
  $(document).ready(function(){
    $("form").submit(function(e) {
      $(e.target).find('button[type="submit"').attr('disabled', true);
      $(e.target).find('input[type="submit"').attr('disabled', true);
      return true;
    });

    setupMentions();
  });
