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

$('.vote-button').click(function(){
    //the button that was clicked (upvote or downvote)
    var elem = $(this);

    // the div holding upvote and downvote buttons
    var parent = elem.parent(".vote-control")
    
    //if upvote button was clicked, sibling is the downvote button
    var sibling = $(elem.siblings(".vote-button")[0]);

    var objectType = parent.data("object-type");
    var objectId = parent.data("object-id");
    
    var state = elem.attr("data-state");
    var isUpvoteButton = elem.hasClass("upvote");
    var isDownvoteButton = elem.hasClass("downvote");
    var action;
    if (isUpvoteButton && state === 'enabled') {
        action = "upvote";
    }
    else if (isDownvoteButton && state === 'enabled') {
        action = "downvote";
    }
    else if (state === 'voted') {
        action = "undovote";
    }
    else {
        // upvote and downvote are both disabled
        // so do nothing
        return;
    }

    // Optimistic UI
    // First update the UI, assuming that the request will succeed
    // If the request fails, revert the UI
    if (action === "upvote" || action === "downvote") {
        elem.attr("data-state", "voted");
        sibling.attr("data-state", "disabled");
    }
    else if (action === "undovote") {
        elem.attr("data-state", "enabled");
        sibling.attr("data-state", "enabled");
    }

    var url = "/api/" + objectType + "/" + objectId + "/" + action;
    
    var csrftoken = getCookie('csrftoken');
    $.post(url, {'csrfmiddlewaretoken': csrftoken })
        .done(function(data){
            //Nothing to do
        })
        .fail(function(data){
            // Undo the changes we made to the UI, thinking that the request would succeed
            if (action === "upvote" || action === "downvote") {
                elem.attr("data-state", "enabled");
                sibling.attr("data-state", "enabled");
            }
            else if (action === "undovote") {
                elem.attr("data-state", "voted");
                sibling.attr("data-state", "disabled");
            }
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