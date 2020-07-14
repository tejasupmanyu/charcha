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

  /* Disable submit button once clicked to prevent accidental double submission */
  $(document).ready(function(){
    $("form").submit(function(e) {
      $(e.target).find('button[type="submit"').attr('disabled', true);
      $(e.target).find('input[type="submit"').attr('disabled', true);
      return true;
    });
  });

  $(document).ready(function(){
    $('a[data-action="reply-to-comment"]').click(function(e) {
      e.preventDefault();
      var anchor = $(e.target);
      var parentCommentId = anchor.data("comment-id");
      var template = $("#reply-template").html();
      var html = template.replace(new RegExp("<<commentid>>"), parentCommentId)
      
      var commentContainer = $('div[data-container="subcomments-' + parentCommentId + '"]').first();
      commentContainer.append(html);
      commentContainer.find('button[data-action="cancel-reply"]').click(function(e) {
        var replyButton = $(e.target);
        var replyFormContainer = replyButton.parents('div[data-container="reply-form"]').first();
        replyFormContainer.remove();
      });
      anchor.remove();
      return true;
    });
  });

/*
* Code to detect if a user has read a post
* CREDIT: https://stackoverflow.com/a/7557433/242940
*/
function isElementInViewport (el) {
  // Special bonus for those using jQuery
  if (typeof jQuery === "function" && el instanceof jQuery) {
      el = el[0];
  }
  var rect = el.getBoundingClientRect();
  return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && /* or $(window).height() */
      rect.right <= (window.innerWidth || document.documentElement.clientWidth) /* or $(window).width() */
  );
}

function onceUserHasReadPost(callback) {
  var visibilityOfPost = {};
  $("div.post.unread").each(function(index, el){
    var postId = el.id;
    visibilityOfPost[postId] = false;
  });
  return function () {
    $("div.post.unread").each(function(index, el) {
      var postId = el.id;
      var oldVisible = visibilityOfPost[postId];
      if (oldVisible) {
        return;
      }
      var visible = isElementInViewport(el);
      if (visible) {
        visibilityOfPost[postId] = true;
        callback(postId);
      }
    });
  }
}

// Add scroll handler only if we are on the posts page
$(document).ready(function(){
  if ($("div.post-details").length > 0) {
    var userReadPostHandler = onceUserHasReadPost(function(postId) {
      console.log("Read Post " + postId)
    });
    $(window).on('DOMContentLoaded load resize scroll', userReadPostHandler);
  }
});

